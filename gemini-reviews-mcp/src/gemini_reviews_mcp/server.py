#!/usr/bin/env python3
"""
Gemini PR Reviews MCP Server
Fetch Gemini Code Assist reviews from GitHub PRs
"""

import asyncio
import os
import sys
import logging
import json
from typing import Any, List, Dict, Optional
from datetime import datetime
import requests
from urllib.parse import urlparse
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiPRReviewsMCPServer:
    def __init__(self):
        self.server = Server("gemini-reviews-mcp")
        self.github_token = os.getenv("GITHUB_TOKEN")
        self.headers = {
            'Accept': 'application/vnd.github.v3+json',
        }
        if self.github_token:
            self.headers['Authorization'] = f'token {self.github_token}'
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools"""
            return [
                Tool(
                    name="get_gemini_reviews",
                    description="Get Gemini Code Assist reviews from a GitHub PR. Can fetch all reviews or only those after your last '/gemini review' comment",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repo": {
                                "type": "string",
                                "description": "Repository name or owner/repo format. If owner is not provided, uses authenticated user (e.g., 'YtbMp3Indir' or 'owner/YtbMp3Indir')"
                            },
                            "pr": {
                                "type": "integer",
                                "description": "PR number (optional - will use last PR if not specified)"
                            },
                            "after_last_review": {
                                "type": "boolean",
                                "description": "If true, only fetch reviews after your last '/gemini review' comment (default: true)",
                                "default": True
                            },
                            "username": {
                                "type": "string",
                                "description": "GitHub username (optional - only used when after_last_review is true)"
                            }
                        },
                        "required": ["repo"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            try:
                if name == "get_gemini_reviews":
                    repo = arguments["repo"]
                    
                    # If repo doesn't contain '/', prepend authenticated user
                    if '/' not in repo:
                        auth_user = self.get_authenticated_user()
                        if auth_user:
                            repo = f"{auth_user}/{repo}"
                            logger.info(f"Auto-detected repo owner: {auth_user}")
                        else:
                            return [TextContent(type="text", text="Error: Could not determine repository owner. Please provide full repo path (owner/repo).")]
                    
                    pr = arguments.get("pr")
                    after_last_review = arguments.get("after_last_review", True)  # Default to True
                    username = arguments.get("username")
                    
                    if after_last_review:
                        return await self.handle_get_gemini_reviews_after_last(
                            repo, pr, username
                        )
                    else:
                        # Get all reviews
                        return await self.handle_get_all_gemini_reviews(
                            repo, pr
                        )
                
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except Exception as e:
                logger.error(f"Error in tool call: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def handle_get_all_gemini_reviews(self, repo: str, pr: Optional[int]) -> List[TextContent]:
        """Handle getting all Gemini reviews from a PR"""
        try:
            logger.info(f"🚀 Getting all Gemini reviews for {repo}")
            
            # Get last PR if not specified
            if pr is None:
                pr = self.find_last_pr(repo)
                if not pr:
                    return [TextContent(type="text", text="Error: Could not find last PR. Please provide pr parameter.")]
                logger.info(f"✅ Found last PR: #{pr}")
            
            # Fetch all Gemini comments
            all_gemini_comments = []
            
            # Fetch PR reviews with pagination
            logger.info(f"🔍 Fetching all reviews from {repo} PR #{pr}...")
            page = 1
            while True:
                url = f"https://api.github.com/repos/{repo}/pulls/{pr}/reviews?page={page}&per_page=100"
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    reviews = response.json()
                    if not reviews:
                        break
                    
                    for review in reviews:
                        if review.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                            all_gemini_comments.append({
                                'type': 'review',
                                'date': review.get('submitted_at'),
                                'state': review['state'],
                                'body': review['body'],
                                'html_url': review['html_url']
                            })
                    page += 1
                else:
                    logger.warning(f"Error fetching reviews: {response.status_code}")
                    break
            
            # Fetch review comments (line comments) with pagination
            logger.info(f"🔍 Fetching all review comments from {repo} PR #{pr}...")
            page = 1
            while True:
                url = f"https://api.github.com/repos/{repo}/pulls/{pr}/comments?page={page}&per_page=100"
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    comments = response.json()
                    if not comments:
                        break
                    
                    for comment in comments:
                        if comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                            all_gemini_comments.append({
                                'type': 'line_comment',
                                'date': comment['created_at'],
                                'file': comment.get('path'),
                                'line': comment.get('line'),
                                'body': comment['body'],
                                'html_url': comment['html_url']
                            })
                    page += 1
                else:
                    logger.warning(f"Error fetching review comments: {response.status_code}")
                    break
            
            # Fetch issue comments with pagination
            logger.info(f"🔍 Fetching all issue comments from {repo} PR #{pr}...")
            page = 1
            while True:
                url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments?page={page}&per_page=100"
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    comments = response.json()
                    if not comments:
                        break
                    
                    for comment in comments:
                        if comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                            all_gemini_comments.append({
                                'type': 'issue_comment',
                                'date': comment['created_at'],
                                'body': comment['body'],
                                'html_url': comment['html_url']
                            })
                    page += 1
                else:
                    logger.warning(f"Error fetching issue comments: {response.status_code}")
                    break
            
            # Sort by type priority and date
            type_priority = {'review': 0, 'line_comment': 1, 'issue_comment': 2}
            all_gemini_comments.sort(key=lambda x: (type_priority.get(x['type'], 3), x['date']))
            
            if not all_gemini_comments:
                return [TextContent(type="text", text=f"❌ No Gemini Code Assist reviews found in PR #{pr}")]
            
            logger.info(f"🤖 Found {len(all_gemini_comments)} total Gemini comments")
            
            # Return raw JSON data
            return [TextContent(type="text", text=json.dumps(all_gemini_comments, indent=2, ensure_ascii=False))]
            
        except Exception as e:
            logger.error(f"Error in handle_get_all_gemini_reviews: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    
    def get_authenticated_user(self) -> str:
        """Get authenticated GitHub user"""
        try:
            response = requests.get("https://api.github.com/user", headers=self.headers)
            if response.status_code == 200:
                return response.json()['login']
        except:
            pass
        return None
    
    def find_last_pr(self, repo: str) -> Optional[int]:
        """Find the last PR number in the repository"""
        try:
            url = f"https://api.github.com/repos/{repo}/pulls?state=all&sort=created&direction=desc&per_page=1"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200 and response.json():
                return response.json()[0]['number']
        except:
            pass
        return None
    
    def find_last_gemini_review_request(self, repo: str, pr: int, username: str) -> Optional[str]:
        """Find the last '/gemini review' comment by the user"""
        logger.info(f"🔍 Searching for last '/gemini review' comment by {username} in PR #{pr}")
        
        try:
            # Fetch all issue comments with pagination
            all_comments = []
            page = 1
            while True:
                url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments?page={page}&per_page=100"
                response = requests.get(url, headers=self.headers)
                if response.status_code == 200:
                    comments = response.json()
                    if not comments:
                        break
                    all_comments.extend(comments)
                    page += 1
                else:
                    break
            
            # Filter and sort
            gemini_review_comments = []
            for comment in all_comments:
                if (comment.get('user', {}).get('login') == username and 
                    '/gemini review' in comment.get('body', '').lower()):
                    gemini_review_comments.append({
                        'date': comment['created_at'],
                        'body': comment['body']
                    })
            
            if not gemini_review_comments:
                logger.info("❌ '/gemini review' comment not found, using default date")
                return "2025-08-01T00:00:00Z"
            
            # Get the most recent one
            gemini_review_comments.sort(key=lambda x: x['date'], reverse=True)
            last_review = gemini_review_comments[0]
            
            logger.info(f"✅ Found last '/gemini review' comment: {last_review['date']}")
            logger.info(f"   Content: {last_review['body']}")
            
            return last_review['date']
            
        except Exception as e:
            logger.error(f"Error finding last review request: {e}")
            return "2025-08-01T00:00:00Z"
    
    def fetch_gemini_comments_after(self, repo: str, pr: int, after_date: str) -> List[Dict]:
        """Fetch all Gemini bot comments after a specific date"""
        all_gemini_comments = []
        cutoff_time = datetime.fromisoformat(after_date.replace('Z', '+00:00'))
        
        logger.info(f"🔍 Fetching Gemini comments after {after_date} for PR #{pr}")
        logger.info(f"🔍 Cutoff time: {cutoff_time}")
        
        # Fetch PR reviews with pagination
        logger.info(f"🔍 Fetching reviews from {repo} PR #{pr}...")
        page = 1
        while True:
            url = f"https://api.github.com/repos/{repo}/pulls/{pr}/reviews?page={page}&per_page=100"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                reviews = response.json()
                if not reviews:
                    break
                
                for review in reviews:
                    if review.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                        # Use submitted_at for reviews, not created_at
                        date_field = review.get('submitted_at')
                        if not date_field:
                            logger.warning(f"⚠️  Review missing submitted_at field: {review.keys()}")
                            continue
                        
                        review_time = datetime.fromisoformat(date_field.replace('Z', '+00:00'))
                        logger.info(f"🤖 Gemini review found: {date_field} | Status: {'✅ INCLUDED' if review_time >= cutoff_time else '❌ EXCLUDED'}")
                        
                        if review_time >= cutoff_time:
                            all_gemini_comments.append({
                                'type': 'review',
                                'date': date_field,
                                'state': review['state'],
                                'body': review['body'],
                                'html_url': review['html_url']
                            })
                page += 1
            else:
                logger.warning(f"Error fetching reviews: {response.status_code}")
                break
        
        # Fetch review comments (line comments) with pagination
        logger.info(f"🔍 Fetching review comments from {repo} PR #{pr}...")
        page = 1
        while True:
            url = f"https://api.github.com/repos/{repo}/pulls/{pr}/comments?page={page}&per_page=100"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                comments = response.json()
                if not comments:
                    break
                
                for comment in comments:
                    if comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                        comment_time = datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00'))
                        if comment_time >= cutoff_time:
                            all_gemini_comments.append({
                                'type': 'line_comment',
                                'date': comment['created_at'],
                                'file': comment.get('path'),
                                'line': comment.get('line'),
                                'body': comment['body'],
                                'html_url': comment['html_url']
                            })
                page += 1
            else:
                logger.warning(f"Error fetching review comments: {response.status_code}")
                break
        
        # Fetch issue comments with pagination
        logger.info(f"🔍 Fetching issue comments from {repo} PR #{pr}...")
        page = 1
        while True:
            url = f"https://api.github.com/repos/{repo}/issues/{pr}/comments?page={page}&per_page=100"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                comments = response.json()
                if not comments:
                    break
                
                for comment in comments:
                    if comment.get('user', {}).get('login') == 'gemini-code-assist[bot]':
                        comment_time = datetime.fromisoformat(comment['created_at'].replace('Z', '+00:00'))
                        if comment_time >= cutoff_time:
                            all_gemini_comments.append({
                                'type': 'issue_comment',
                                'date': comment['created_at'],
                                'body': comment['body'],
                                'html_url': comment['html_url']
                            })
                page += 1
            else:
                logger.warning(f"Error fetching issue comments: {response.status_code}")
                break
        
        # Sort by type priority and date
        type_priority = {'review': 0, 'line_comment': 1, 'issue_comment': 2}
        all_gemini_comments.sort(key=lambda x: (type_priority.get(x['type'], 3), x['date']))
        
        logger.info(f"📊 Summary:")
        reviews_count = len([c for c in all_gemini_comments if c['type'] == 'review'])
        line_comments_count = len([c for c in all_gemini_comments if c['type'] == 'line_comment'])
        issue_comments_count = len([c for c in all_gemini_comments if c['type'] == 'issue_comment'])
        logger.info(f"   📝 Reviews: {reviews_count}")
        logger.info(f"   💬 Line Comments: {line_comments_count}")
        logger.info(f"   🗨️  Issue Comments: {issue_comments_count}")
        logger.info(f"   📅 After date: {after_date}")
        
        return all_gemini_comments
    
    
    async def handle_get_gemini_reviews_after_last(self, repo: str, pr: Optional[int], username: Optional[str]) -> List[TextContent]:
        """Handle get_gemini_reviews_after_last tool call"""
        try:
            logger.info(f"🚀 Starting get_gemini_reviews_after_last for {repo}")
            
            # Get authenticated user if not specified
            if not username:
                username = self.get_authenticated_user()
                if not username:
                    return [TextContent(type="text", text="Error: Could not determine GitHub user. Please provide username parameter.")]
                logger.info(f"✅ Using authenticated user: {username}")
            
            # Get last PR if not specified
            if pr is None:
                pr = self.find_last_pr(repo)
                if not pr:
                    return [TextContent(type="text", text="Error: Could not find last PR. Please provide pr parameter.")]
                logger.info(f"✅ Found last PR: #{pr}")
            
            # Find last /gemini review comment
            last_review_date = self.find_last_gemini_review_request(repo, pr, username)
            logger.info(f"📅 Last review date: {last_review_date}")
            
            # Fetch Gemini comments after that date
            gemini_comments = self.fetch_gemini_comments_after(repo, pr, last_review_date)
            
            if not gemini_comments:
                return [TextContent(type="text", text=f"❌ No Gemini Code Assist reviews found after {username}'s last comment at {last_review_date}")]
            
            logger.info(f"🤖 Found {len(gemini_comments)} Gemini comments after last review")
            
            # Return raw JSON data
            return [TextContent(type="text", text=json.dumps(gemini_comments, indent=2, ensure_ascii=False))]
            
        except Exception as e:
            logger.error(f"Error in handle_get_gemini_reviews_after_last: {e}")
            return [TextContent(type="text", text=f"Error: {str(e)}")]

async def main():
    """Main function to run the MCP server"""
    server = GeminiPRReviewsMCPServer()
    
    async with stdio_server() as (read_stream, write_stream):
        await server.server.run(
            read_stream,
            write_stream,
            server.server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())