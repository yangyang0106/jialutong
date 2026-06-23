const STORAGE_KEY = "tripProgress";

function getTripProgress(routeId) {
  const allProgress = wx.getStorageSync(STORAGE_KEY) || {};
  return allProgress[routeId] || null;
}

function saveTripProgress(routeId, currentStepIndex, tripId) {
  const allProgress = wx.getStorageSync(STORAGE_KEY) || {};
  allProgress[routeId] = {
    currentStepIndex,
    tripId: tripId || allProgress[routeId] && allProgress[routeId].tripId || "",
    updatedAt: Date.now()
  };
  wx.setStorageSync(STORAGE_KEY, allProgress);
}

function clearTripProgress(routeId) {
  const allProgress = wx.getStorageSync(STORAGE_KEY) || {};
  delete allProgress[routeId];
  wx.setStorageSync(STORAGE_KEY, allProgress);
}

module.exports = {
  getTripProgress,
  saveTripProgress,
  clearTripProgress
};
