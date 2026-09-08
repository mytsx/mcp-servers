// Smoke test: drives the server in-process over an in-memory transport.
// No browser is launched — the terminal-dependent tools are checked for the
// error they must return when nothing is open.
import assert from 'node:assert/strict';

process.env.TERMINAL_URL = 'https://terminal.example.invalid/';

const { InMemoryTransport } = await import('@modelcontextprotocol/server');
const { Client } = await import('@modelcontextprotocol/client');
const { server } = await import('../server.js');

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

const { prompts } = await client.listPrompts();
console.log('PROMPTS:', prompts.map((p) => p.name).join(', '));
assert.equal(prompts.length, 1);

await client.close();
console.log('smoke: OK');
