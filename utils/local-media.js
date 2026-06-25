const LOCAL_HTTP_MEDIA_RE = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//;
const resolvedCache = {};

function isLocalHttpMediaUrl(url) {
  return LOCAL_HTTP_MEDIA_RE.test(String(url || ""));
}

function resolveLocalHttpMediaUrl(url) {
  if (!isLocalHttpMediaUrl(url)) return Promise.resolve(url || "");
  if (resolvedCache[url]) return Promise.resolve(resolvedCache[url]);
  if (typeof wx === "undefined" || !wx.downloadFile) return Promise.resolve(url);

  return new Promise((resolve) => {
    wx.downloadFile({
      url,
      success: (result) => {
        const statusCode = Number(result.statusCode || 0);
        if (statusCode >= 200 && statusCode < 300 && result.tempFilePath) {
          resolvedCache[url] = result.tempFilePath;
          resolve(result.tempFilePath);
          return;
        }
        resolve(url);
      },
      fail: () => resolve(url)
    });
  });
}

function resolveStepImageForDisplay(step) {
  const imageUrl = step && step.imageUrl || "";
  return resolveLocalHttpMediaUrl(imageUrl).then((displayImageUrl) => ({
    ...step,
    displayImageUrl
  }));
}

function resolveRouteImagesForDisplay(route) {
  if (!route || !Array.isArray(route.steps)) return Promise.resolve(route);
  return Promise.all(route.steps.map(resolveStepImageForDisplay)).then((steps) => ({
    ...route,
    steps
  }));
}

module.exports = {
  isLocalHttpMediaUrl,
  resolveLocalHttpMediaUrl,
  resolveRouteImagesForDisplay,
  resolveStepImageForDisplay
};
