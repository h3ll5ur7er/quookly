import { claim } from './support';
import { expect, test } from '@playwright/test';

/**
 * The MCP surface, against a running instance (ADR-068).
 *
 * The backend tests drive a freshly built surface directly, because a session manager may
 * be started once and every one of those tests has its own event loop. What none of them
 * can show is the thing the decision actually claims: that this is **mounted in the
 * application**, started by its lifespan, reachable at `/mcp` on the same port and behind
 * the same token as everything else. A surface that is built but never wired looks exactly
 * like one that is, from inside.
 *
 * Spoken by hand rather than with the SDK — this suite is TypeScript and the client is
 * Python, and the wire format is three JSON-RPC messages. What is being checked here is
 * the wiring, not the protocol library.
 */

const PROTOCOL = '2025-06-18';

let headers: Record<string, string>;

test.beforeAll(async ({ request }) => {
  headers = {
    Authorization: `Bearer ${await claim(request)}`,
    Accept: 'application/json, text/event-stream',
    'Content-Type': 'application/json',
  };
});

/** The body of an event-stream reply, which is how this transport answers. */
function said(body: string): Record<string, unknown> {
  const line = body.split('\n').find((one) => one.startsWith('data:'));
  expect(line, `no data in ${body.slice(0, 200)}`).toBeTruthy();
  return JSON.parse(line!.slice('data:'.length)) as Record<string, unknown>;
}

test('an agent can shake hands with the kitchen', async ({ request }) => {
  const opened = await request.post('/mcp', {
    headers,
    data: {
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: PROTOCOL,
        capabilities: {},
        clientInfo: { name: 'a-test', version: '1' },
      },
    },
  });

  expect(opened.status(), await opened.text()).toBe(200);
  const answer = said(await opened.text()) as { result: { serverInfo: { name: string } } };
  expect(answer.result.serverInfo.name).toBe('quookly');
});

test('it refuses an agent with no token', async ({ request }) => {
  /* One token is one cook. An agent arriving without one is not shown a household's
     pantry — and the tool says so rather than answering emptily. */
  const opened = await request.post('/mcp', {
    headers: { Accept: 'application/json, text/event-stream', 'Content-Type': 'application/json' },
    data: {
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: PROTOCOL,
        capabilities: {},
        clientInfo: { name: 't', version: '1' },
      },
    },
  });
  expect(opened.status()).toBe(200);

  const session = opened.headers()['mcp-session-id'];
  expect(session, 'the transport should have opened a session').toBeTruthy();

  const asked = await request.post('/mcp', {
    headers: {
      Accept: 'application/json, text/event-stream',
      'Content-Type': 'application/json',
      'mcp-session-id': session,
      'mcp-protocol-version': PROTOCOL,
    },
    data: {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: { name: 'what_is_in_the_pantry', arguments: {} },
    },
  });

  const answer = said(await asked.text()) as {
    result?: { isError?: boolean; is_error?: boolean; content?: { text?: string }[] };
    error?: unknown;
  };
  const complaint = JSON.stringify(answer);
  expect(complaint).toContain('token');
});
