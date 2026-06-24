// 生产包不内置真实家庭路线。
// 老人端优先读取服务端已发布路线，其次读取上次缓存。
// 如需本地离线演示，可运行 scripts/sync-validated-demo-route.js 生成临时演示数据，
// 并在 config/upload.local.js 中显式设置 enableLocalDemoRoutes: true。
const routes = {};

function getRouteById(id) {
  return Object.values(routes).find((route) => route.id === id);
}

module.exports = {
  routes,
  getRouteById
};
