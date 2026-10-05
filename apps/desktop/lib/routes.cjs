const routes = [
  {method: "GET", pattern: /^\/(health|v1\/(status|tools|sessions))$/},
  {method: "GET", pattern: /^\/v1\/sessions\/[a-f0-9]{32}$/},
  {method: "POST", pattern: /^\/v1\/(run|computer\/run|sessions)$/},
  {method: "POST", pattern: /^\/v1\/settings\/computer-control$/},
  {method: "POST", pattern: /^\/v1\/sessions\/[a-f0-9]{32}\/resume$/},
  {method: "DELETE", pattern: /^\/v1\/sessions\/[a-f0-9]{32}$/},
];

function allowedRoute(method, route) {
  return routes.some((item) => item.method === method && item.pattern.test(route));
}

module.exports = {allowedRoute};
