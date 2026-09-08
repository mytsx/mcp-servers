// Smoke test: drives the server in-process over an in-memory transport,
// with a stub GİB worker standing in for the real API.
import { createServer } from 'node:http';
import assert from 'node:assert/strict';

const stub = createServer((req, res) => {
  let body = '';
  req.on('data', (chunk) => (body += chunk));
  req.on('end', () => {
    const params = JSON.parse(body || '{}');
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(
      JSON.stringify({
        hesaplamaList: [
          {
            odenecekMiktar: params.odenecekMiktar,
            vadeTarihi: params.vadeTarihi,
            odemeTarihi: params.odemeTarihi,
            hesaplananZamOrani: '%14,50',
            hesaplananFaizTutari: '145,00',
            hesaplananMiktar: '1145,00',
          },
        ],
      })
    );
  });
});
// Port 0: an ephemeral port, so parallel runs cannot collide on EADDRINUSE.
await new Promise((resolve) => stub.listen(0, '127.0.0.1', resolve));

process.env.GIB_API_URL = `http://127.0.0.1:${stub.address().port}`;
const ENTRY_POINT = '../index.js';
const ENTRY_ENV = { GIB_API_URL: process.env.GIB_API_URL };

const { Client } = await import('@modelcontextprotocol/client');
const { InMemoryTransport } = await import('@modelcontextprotocol/client');
const { buildServer } = await import('../index.js');

const server = buildServer();
const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
const client = new Client({ name: 'smoke', version: '1.0.0' });
await Promise.all([server.connect(serverTransport), client.connect(clientTransport)]);

const { tools } = await client.listTools();
console.log('TOOLS:', tools.map((t) => t.name).join(', '));
assert.deepEqual(
  tools.map((t) => t.name).sort(),
  ['calculate_gecikme_faizi', 'calculate_gecikme_zammi']
);
assert.ok(tools[0].outputSchema, 'tool should advertise an outputSchema');
assert.equal(tools[0].annotations.readOnlyHint, true);

const ok = await client.callTool({
  name: 'calculate_gecikme_zammi',
  arguments: { odenecekMiktar: '1000.00', vadeTarihi: '20260101', odemeTarihi: '20260301' },
});
console.log('STRUCTURED:', JSON.stringify(ok.structuredContent));
assert.equal(ok.structuredContent.tip, 'Gecikme Zammı');
assert.equal(ok.structuredContent.toplamOdenecek, '1145,00');
assert.ok(ok.content[0].text.includes('Toplam Ödenecek'));

const bad = await client.callTool({
  name: 'calculate_gecikme_faizi',
  arguments: { odenecekMiktar: '1000', vadeTarihi: '2026-01-01', odemeTarihi: '20260601' },
});
console.log('BAD DATE isError:', bad.isError, '|', bad.content[0].text.slice(0, 70));
assert.equal(bad.isError, true);

// Eight digits is not enough: the date has to exist.
for (const bad of ['20260231', '20261301', '00000000', '20260100']) {
  const result = await client.callTool({
    name: 'calculate_gecikme_zammi',
    arguments: { odenecekMiktar: '1000.00', vadeTarihi: bad, odemeTarihi: '20260301' },
  });
  assert.equal(result.isError, true, `${bad} kabul edilmemeliydi`);
}
console.log('IMPOSSIBLE DATES: rejected');

// A leap day that does exist must still go through.
const leap = await client.callTool({
  name: 'calculate_gecikme_zammi',
  arguments: { odenecekMiktar: '1000.00', vadeTarihi: '20240229', odemeTarihi: '20240301' },
});
assert.ok(!leap.isError, '20240229 geçerli bir tarih');
console.log('LEAP DAY: accepted');

// The prompt validates its arguments the same way the tools do.
const badPrompt = await client
  .getPrompt({ name: 'gecikme_karsilastir', arguments: { odenecekMiktar: '1000', vadeTarihi: '20260231', odemeTarihi: '20260301' } })
  .then(() => null, (error) => error);
assert.ok(badPrompt, 'takvimde olmayan tarih prompt tarafından da reddedilmeliydi');
console.log('PROMPT VALIDATION: rejected');

const { prompts } = await client.listPrompts();
console.log('PROMPTS:', prompts.map((p) => p.name).join(', '));
assert.equal(prompts.length, 1);

await client.close();
stub.close();

// The installed entry point must actually start the server. npm links the bin
// into node_modules/.bin, so process.argv[1] is that symlink while
// import.meta.url is the real file: comparing them unresolved made an installed
// server exit silently while running the file directly worked fine.
{
  const { execFileSync } = await import('node:child_process');
  const { mkdtempSync, rmSync, symlinkSync, realpathSync } = await import('node:fs');
  const { tmpdir } = await import('node:os');
  const nodePath = await import('node:path');
  const { fileURLToPath } = await import('node:url');

  const entry = realpathSync(fileURLToPath(new URL(ENTRY_POINT, import.meta.url)));
  const linkDir = mkdtempSync(nodePath.join(tmpdir(), 'binlink-'));
  const link = nodePath.join(linkDir, 'server-link.mjs');
  symlinkSync(entry, link);

  try {
    const request =
      JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'server/discover', params: {} }) + '\n';
    const stdout = execFileSync(process.execPath, [link], {
      input: request,
      env: { ...process.env, ...ENTRY_ENV },
      encoding: 'utf8',
      timeout: 30000,
    });
    assert.ok(stdout.trim().length > 0, 'symlink üzerinden çalıştırılan sunucu yanıt vermeli');
    assert.ok(stdout.includes('"jsonrpc"'), stdout.slice(0, 200));
    console.log('BIN SYMLINK: server responds');
  } finally {
    rmSync(linkDir, { recursive: true, force: true });
  }
}

console.log('smoke: OK');
