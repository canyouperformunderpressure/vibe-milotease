(function () {
  'use strict';
  var iframe = document.querySelector('.eosIframe');
  var projectId = window.MILO_PROJECT_ID;
  var script = null;

  var methods = {
    load: function () {
      return fetch('/preview/' + encodeURIComponent(projectId) + '/eosscript.json', {cache: 'no-store'})
        .then(function (response) { return response.json(); })
        .then(function (value) {
          script = value;
          return {title: window.MILO_TITLE, author: window.MILO_AUTHOR, script: value, preview: true};
        });
    },
    queryMedia: function (params) {
      var query = new URLSearchParams({
        url: params.locator,
        size: params.size || 'l',
        type: params.type || '',
        projectId: projectId
      });
      return fetch('/media/query.php?' + query).then(function (response) { return response.json(); });
    },
    loadStorage: function () {
      return fetch('/graphql/', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query: 'query loadTeaseStorage($teaseId: ID!) { loadTeaseStorage(teaseId: $teaseId) { data } }', variables: {teaseId: projectId}})
      }).then(function (response) { return response.json(); }).then(function (value) { return value.data.loadTeaseStorage.data; });
    },
    saveStorage: function (params) {
      return fetch('/graphql/', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({query: 'mutation saveTeaseStorage($teaseId: ID!, $data: String!) { saveTeaseStorage(teaseId: $teaseId, data: $data) }', variables: {teaseId: projectId, data: params.state}})
      }).then(function (response) { return response.json(); }).then(function () { return true; });
    },
    openRatingDialog: function () { return true; },
    goToAuthor: function () { return true; }
  };

  window.addEventListener('message', function (event) {
    if (!iframe || event.source !== iframe.contentWindow || !event.data || !event.data.method) return;
    var id = event.data.id;
    var method = methods[event.data.method];
    if (!method) return;
    Promise.resolve(method(event.data.params || {})).then(function (result) {
      iframe.contentWindow.postMessage({jsonrpc: '2.0', result: result, id: id}, '*');
    }).catch(function (error) {
      iframe.contentWindow.postMessage({jsonrpc: '2.0', error: {message: error.message}, id: id}, '*');
    });
  });
})();

