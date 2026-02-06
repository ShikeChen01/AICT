/**
 * Mock acquireVsCodeApi for E2E tests. Provides empty workspace (blank canvas)
 * and logs RPC calls for assertions.
 */
(function () {
  'use strict';

  window.__rpcLog = [];
  window.__lastSave = null;

  window.acquireVsCodeApi = function () {
    var state = {};
    return {
      postMessage: function (msg) {
        window.__rpcLog.push(msg);
        if (msg && msg.kind === 'aict-rpc' && msg.payload) {
          var payload = msg.payload;
          var id = payload.id;
          var method = payload.method;
          var result;
          if (method === 'loadWorkspaceState') {
            result = { entities: [], canvas: undefined };
          } else if (method === 'saveWorkspaceState') {
            window.__lastSave = payload.params || null;
            result = { ok: true };
          } else if (method === 'listWorkspaceFiles') {
            result = { files: [] };
          } else {
            result = undefined;
          }
          setTimeout(function () {
            window.postMessage(
              { kind: 'aict-rpc', payload: { id: id, result: result } },
              '*'
            );
          }, 10);
        }
      },
      getState: function () {
        return state;
      },
      setState: function (s) {
        state = s;
      },
    };
  };
})();
