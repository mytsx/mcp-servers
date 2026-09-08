// Smoke test: drives the server in-process over an in-memory transport.
// No browser is launched — the terminal-dependent tools are checked for the
// error they must return when nothing is open.
import assert from 'node:assert/strict';

import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

process.env.TERMINAL_URL = 'https://terminal.example.invalid/';
// Never touch the real saved session: clear_session below deletes this file.
const sessionDir = await fs.mkdtemp(path.join(os.tmpdir(), 'asger-smoke-'));
process.env.SESSION_FILE = path.join(sessionDir, 'session-state.json');

const { InMemoryTransport } = await import('@modelcontextprotocol/server');
const { z } = await import('zod');
const { Client } = await import('@modelcontextprotocol/client');
const { buildServer } = await import('../server.js');
const server = buildServer();

const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
const client = new Client({ name: 'smoke', version: '1.0.0' });
await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);

const { tools } = await client.listTools();
const names = tools.map((t) => t.name).sort();
console.log('TOOLS:', names.join(', '));
assert.deepEqual(names, [
  'clear_session',
  'disconnect',
  'execute_and_read',
  'execute_command',
  'extract_text',
  'open_terminal',
  'save_session',
  'take_screenshot',
]);

for (const tool of tools) {
  assert.ok(tool.outputSchema, `${tool.name} should advertise an outputSchema`);
  assert.ok(tool.annotations, `${tool.name} should carry annotations`);
}

const noTerminal = await client.callTool({
  name: 'execute_command',
  arguments: { command: 'uptime' },
});
console.log('NO TERMINAL isError:', noTerminal.isError, '|', noTerminal.content[0].text.slice(0, 60));
assert.equal(noTerminal.isError, true);

const badArgs = await client.callTool({ name: 'execute_command', arguments: { command: '' } });
console.log('EMPTY COMMAND isError:', badArgs.isError);
assert.equal(badArgs.isError, true);

// disconnect is safe with nothing open, and reports that.
const idle = await client.callTool({ name: 'disconnect', arguments: {} });
console.log('DISCONNECT:', JSON.stringify(idle.structuredContent));
assert.equal(idle.structuredContent.wasOpen, false);

const cleared = await client.callTool({ name: 'clear_session', arguments: {} });
console.log('CLEAR SESSION existed:', cleared.structuredContent.existed);
assert.equal(cleared.structuredContent.existed, false, 'the temp session file should not exist');
assert.ok(
  cleared.structuredContent.sessionFile.startsWith(sessionDir),
  'the server must honour SESSION_FILE, not delete the checked-out session'
);

// Destructive commands must be recognised however the flags are spelled.
// `rm --recursive --force` used to slip past a pattern that only matched `-rf`.
const { destructiveReason } = await import('../server.js');
for (const command of [
  'rm -rf /tmp/x',
  'rm -r -f /tmp/x',
  'rm --recursive --force /tmp/x',
  'rm --force /tmp/x',
  'rm -v -r /tmp/x',
  'rm --verbose --recursive /tmp/x',
  'rm -i -r /tmp/x',
  'rm --interactive=never -r /tmp/x',
  'rm /tmp/missing -rf /tmp/x',
  'chmod --reference=/etc/passwd -R /tmp/x',
  'echo hi; rm -rf /tmp/x',
  'true && rm -r /tmp/x',
  'reboot',
  'docker system prune -f',
]) {
  assert.ok(destructiveReason(command), `${command} yıkıcı sayılmalıydı`);
}
for (const command of ['ls -la', 'rm --help', 'rm file.txt', 'cat /etc/motd']) {
  assert.equal(destructiveReason(command), null, `${command} yıkıcı sayılmamalıydı`);
}
console.log('DESTRUCTIVE PATTERNS: ok');

// A tool registered without an inputSchema receives the request context as its
// single argument — this is what extract_text relies on to report OCR progress.
// Proven here rather than asserted, because two reviewers read it the other way.
{
  const { McpServer } = await import('@modelcontextprotocol/server');
  const probe = new McpServer({ name: 'probe', version: '1.0.0' });
  probe.registerTool(
    'no_input_tool',
    { description: 'shaped exactly like extract_text', outputSchema: z.object({ ok: z.boolean() }) },
    async (ctx) => {
      const token = ctx?.mcpReq?._meta?.progressToken;
      assert.ok(ctx?.mcpReq, 'tek parametre request context olmalı');
      if (token !== undefined) {
        await ctx.mcpReq.notify({
          method: 'notifications/progress',
          params: { progressToken: token, progress: 1, total: 1, message: 'OCR' },
        });
      }
      return { content: [{ type: 'text', text: 'ok' }], structuredContent: { ok: true } };
    }
  );

  const [probeClientTransport, probeServerTransport] = InMemoryTransport.createLinkedPair();
  const probeClient = new Client({ name: 'probe-client', version: '1.0.0' });
  await Promise.all([
    probe.connect(probeServerTransport),
    probeClient.connect(probeClientTransport),
  ]);

  const progress = [];
  const probed = await probeClient.callTool(
    { name: 'no_input_tool', arguments: {} },
    { onprogress: (event) => progress.push(event) }
  );
  assert.equal(probed.structuredContent.ok, true);
  assert.equal(progress.length, 1, 'ilerleme bildirimi ulaşmalıydı');
  await probeClient.close();
  console.log('NO-INPUT HANDLER: first argument is the context, progress delivered');
}

const { prompts } = await client.listPrompts();
console.log('PROMPTS:', prompts.map((p) => p.name).join(', '));
assert.equal(prompts.length, 1);

await client.close();
await fs.rm(sessionDir, { recursive: true, force: true });
console.log('smoke: OK');
