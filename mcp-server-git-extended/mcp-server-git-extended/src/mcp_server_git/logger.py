import functools
import time
import json
import traceback
from typing import Any, Callable
import asyncio
import logging

import git
import httpx
from sqlmodel import Session

from .models import GitLog, engine, create_db_and_tables
from .async_models import save_log_async, create_db_and_tables_async


# Setup logging
logger = logging.getLogger(__name__)

# Initialize database tables
create_db_and_tables()

# Global HTTP client for notifications
notification_client = httpx.AsyncClient(timeout=1.0)


async def _notify_new_log():
    """Send notification about new log entry via WebSocket"""
    try:
        # Try to notify the web interface about the new log
        # Port detection is handled by the web interface
        for port in range(5555, 5565):  # Try a few ports
            try:
                await notification_client.post(f"http://localhost:{port}/api/notify")
                break  # Success, stop trying
            except httpx.RequestError:
                continue  # Try next port
    except Exception as e:
        # Silently fail - notifications are not critical
        logger.debug(f"Failed to send WebSocket notification: {e}")


def log_command(func: Callable) -> Callable:
    """Decorator to log Git command execution"""
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        command_name = func.__name__
        repo_path = None
        
        # Extract repo path if first argument is a git.Repo
        if args and isinstance(args[0], git.Repo):
            try:
                repo_path = str(args[0].working_dir)
            except Exception:
                pass
        
        # Prepare arguments for logging
        log_args = []
        for arg in args:
            if isinstance(arg, git.Repo):
                log_args.append(f"<Repo: {arg.working_dir}>")
            else:
                log_args.append(str(arg))
        
        arguments_str = json.dumps({
            "args": log_args,
            "kwargs": {k: str(v) for k, v in kwargs.items()}
        })
        
        output = None
        error = None
        status = "success"
        
        try:
            # Execute the function
            result = func(*args, **kwargs)
            output = str(result) if result is not None else ""
            return result
            
        except Exception as e:
            status = "error"
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            raise
            
        finally:
            # Calculate duration
            duration = time.time() - start_time
            
            # Save to database
            try:
                with Session(engine) as session:
                    log_entry = GitLog(
                        command=command_name,
                        arguments=arguments_str,
                        output=output,
                        error=error,
                        duration=duration,
                        status=status,
                        repo_path=repo_path
                    )
                    session.add(log_entry)
                    session.commit()
                
                # Send WebSocket notification synchronously from the worker thread
                try:
                    with httpx.Client(timeout=1.0) as client:
                        for port in range(5555, 5565):
                            try:
                                client.post(f"http://localhost:{port}/api/notify")
                                break
                            except httpx.RequestError:
                                continue
                except Exception as notify_error:
                    logger.debug(f"Failed to send WebSocket notification: {notify_error}")
            except Exception as db_error:
                # Don't let logging errors break the application
                logger.error(f"Failed to log command: {db_error}")
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        command_name = func.__name__
        repo_path = None
        
        # Extract repo path if first argument is a git.Repo
        if args and isinstance(args[0], git.Repo):
            try:
                repo_path = str(args[0].working_dir)
            except Exception:
                pass
        
        # Prepare arguments for logging
        log_args = []
        for arg in args:
            if isinstance(arg, git.Repo):
                log_args.append(f"<Repo: {arg.working_dir}>")
            else:
                log_args.append(str(arg))
        
        arguments_str = json.dumps({
            "args": log_args,
            "kwargs": {k: str(v) for k, v in kwargs.items()}
        })
        
        output = None
        error = None
        status = "success"
        
        try:
            # Execute the function
            result = await func(*args, **kwargs)
            output = str(result) if result is not None else ""
            return result
            
        except Exception as e:
            status = "error"
            error = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            raise
            
        finally:
            # Calculate duration
            duration = time.time() - start_time
            
            # Save to database asynchronously
            try:
                log_entry = GitLog(
                    command=command_name,
                    arguments=arguments_str,
                    output=output,
                    error=error,
                    duration=duration,
                    status=status,
                    repo_path=repo_path
                )
                await save_log_async(log_entry)
                
                # Send WebSocket notification
                await _notify_new_log()
            except Exception as db_error:
                # Don't let logging errors break the application
                logger.error(f"Failed to log command: {db_error}")
    
    # Return appropriate wrapper based on function type
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper