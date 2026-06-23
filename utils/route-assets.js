const STORAGE_KEY = "routeStepAssets";

function getAssetKey(routeId, stepNo) {
  return `${routeId}:${stepNo}`;
}

function getAllAssets() {
  return wx.getStorageSync(STORAGE_KEY) || {};
}

function getStepAsset(routeId, stepNo) {
  return getAllAssets()[getAssetKey(routeId, stepNo)] || {};
}

function saveStepAsset(routeId, stepNo, asset) {
  const assets = getAllAssets();
  const key = getAssetKey(routeId, stepNo);
  assets[key] = {
    ...assets[key],
    ...asset
  };
  wx.setStorageSync(STORAGE_KEY, assets);
  return assets[key];
}

function removeStepAsset(routeId, stepNo, field) {
  const assets = getAllAssets();
  const key = getAssetKey(routeId, stepNo);
  if (assets[key]) {
    delete assets[key][field];
    wx.setStorageSync(STORAGE_KEY, assets);
  }
}

function saveStepConfig(routeId, stepNo, config) {
  return saveStepAsset(routeId, stepNo, config);
}

function applyAssetsToRoute(route) {
  return {
    ...route,
    steps: route.steps.map((step) => {
      const configuredStep = {
        ...step,
        ...(route.published ? {} : getStepAsset(route.id, step.stepNo))
      };
      return {
        ...configuredStep,
        imageUrl: configuredStep.imageUrl || configuredStep.image || "",
        image: configuredStep.image || configuredStep.imageUrl || "",
        arriveRadius: Number(configuredStep.arriveRadius) || 30,
        showDirectionDistance: Number(configuredStep.showDirectionDistance) || 30
      };
    })
  };
}

module.exports = {
  getAllAssets,
  getStepAsset,
  saveStepAsset,
  saveStepConfig,
  removeStepAsset,
  applyAssetsToRoute
};
