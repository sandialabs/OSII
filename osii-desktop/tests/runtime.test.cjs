const test = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { RuntimeClient, validRuntimeSession } = require('../runtime-client.cjs');

test('runtime addresses must be private loopback sessions', () => {
  const token = 'x'.repeat(48);
  assert.equal(validRuntimeSession({ url: 'http://127.0.0.1:49152', token }), true);
  for (const url of ['http://localhost:49152', 'http://127.0.0.1', 'https://127.0.0.1:49152',
    'http://user:pass@127.0.0.1:49152', 'http://127.0.0.1:49152/path', 'https://hostile.example']) {
    assert.equal(validRuntimeSession({ url, token }), false, url);
  }
  assert.equal(validRuntimeSession({ url: 'http://127.0.0.1:49152', token: 'short' }), false);
});

test('private RPC matches responses, reports failures and shuts down on EOF', async () => {
  const script = `const readline=require('node:readline');
    console.log(JSON.stringify({event:'supervisor_ready',protocol:1}));
    readline.createInterface({input:process.stdin}).on('line',line=>{
      const value=JSON.parse(line);
      if(value.command==='shutdown') process.exit(0);
      console.log(JSON.stringify(value.command==='fail'?{id:value.id,error:'Explicit library failure'}:{id:value.id,result:{kept:true}}));
    });`;
  const child = spawn(process.execPath, ['-e', script], { stdio: ['pipe', 'pipe', 'ignore'] });
  const client = new RuntimeClient(child);
  try {
    assert.deepEqual(await client.request('profiles'), { kept: true });
    await assert.rejects(client.request('fail'), /Explicit library failure/);
  } finally { await client.shutdown(); }
  assert.equal(client.closed, true);
});

test('a crashed runtime rejects outstanding requests', async () => {
  const child = spawn(process.execPath, ['-e', `console.log(JSON.stringify({event:'supervisor_ready',protocol:1})); process.stdin.once('data',()=>process.exit(7));`],
    { stdio: ['pipe', 'pipe', 'ignore'] });
  const client = new RuntimeClient(child);
  await assert.rejects(client.request('profiles'), /exit 7/);
});
