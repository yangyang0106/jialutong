const {
  createAndSaveRouteDraft,
  prepareRouteAdvice
} = require("../../utils/route-engine/route-service");
const {
  deleteRouteDraft,
  listRouteDrafts,
  reverseGeocode,
  searchPlaces
} = require("../../utils/route-engine/route-repository");
const { requireFamilyLogin } = require("../../utils/auth");

function createRouteId() {
  return `route-${Date.now()}`;
}

Page({
  data: {
    routeName: "",
    elderSlot: "TO_MOM",
    elderSlotOptions: [
      { value: "TO_MOM", label: "首页按钮 1" },
      { value: "TO_HOME", label: "首页按钮 2" }
    ],
    mode: "TRANSIT",
    originKeyword: "",
    destinationKeyword: "",
    originResults: [],
    destinationResults: [],
    origin: null,
    destination: null,
    searchingField: "",
    locatingField: "",
    creating: false,
    advising: false,
    routePlanResponse: null,
    routePlans: [],
    aiAdvice: null,
    recommendedPlan: null,
    deletingRouteId: "",
    drafts: [],
    activeSection: "routes"
  },

  onShow() {
    if (!requireFamilyLogin("/pages/route-create/route-create")) return;
    this.loadDrafts();
  },

  loadDrafts() {
    listRouteDrafts()
      .then(({ routes }) =>
        this.setData({
          drafts: (routes || []).map((route) => ({
            ...route,
            canDelete: route.status !== "PUBLISHED"
          }))
        })
      )
      .catch(() => this.setData({ drafts: [] }));
  },

  showRouteList() {
    this.setData({ activeSection: "routes" });
    this.loadDrafts();
  },

  showCreateForm() {
    this.setData({ activeSection: "create" });
  },

  updateRouteName(event) {
    this.setData({ routeName: event.detail.value });
  },

  updateKeyword(event) {
    const field = event.currentTarget.dataset.field;
    this.setData({
      [`${field}Keyword`]: event.detail.value,
      [field]: null,
      [`${field}Results`]: [],
      routePlanResponse: null,
      routePlans: [],
      aiAdvice: null,
      recommendedPlan: null
    });
  },

  chooseMode(event) {
    this.setData({
      mode: event.currentTarget.dataset.mode,
      routePlanResponse: null,
      routePlans: [],
      aiAdvice: null,
      recommendedPlan: null
    });
  },

  chooseElderSlot(event) {
    const elderSlot = event.currentTarget.dataset.slot;
    this.setData({ elderSlot });
  },

  searchPlace(event) {
    const field = event.currentTarget.dataset.field;
    const keyword = this.data[`${field}Keyword`].trim();
    if (!keyword) {
      wx.showToast({ title: "请先输入地点名称", icon: "none" });
      return;
    }
    this.setData({ searchingField: field });
    searchPlaces(keyword)
      .then(({ places }) => {
        this.setData({
          [`${field}Results`]: places || [],
          searchingField: ""
        });
      })
      .catch((error) => {
        this.setData({ searchingField: "" });
        wx.showModal({
          title: "地点搜索未完成",
          content: error.message || "请稍后再试。",
          showCancel: false,
          confirmText: "知道了"
        });
      });
  },

  selectPlace(event) {
    const { field, index } = event.currentTarget.dataset;
    const place = this.data[`${field}Results`][Number(index)];
    if (!place) return;
    this.setData({
      [field]: place,
      [`${field}Keyword`]: place.name,
      [`${field}Results`]: [],
      routePlanResponse: null,
      routePlans: [],
      aiAdvice: null,
      recommendedPlan: null
    });
    this.fillRouteNameFromDestination(field, place);
  },

  fillRouteNameFromDestination(field, place) {
    if (field !== "destination" || !place || this.data.routeName.trim()) return;
    this.setData({ routeName: `去${place.name}` });
  },

  useCurrentLocation(event) {
    const field = event.currentTarget.dataset.field;
    if (!field || this.data.locatingField) return;
    this.setData({ locatingField: field });
    wx.getLocation({
      type: "gcj02",
      isHighAccuracy: true,
      highAccuracyExpireTime: 5000,
      success: ({ latitude, longitude }) => {
        const location = {
          latitude: Number(latitude),
          longitude: Number(longitude)
        };
        reverseGeocode(location)
          .then(({ place }) => {
            const resolvedPlace = {
              ...place,
              latitude: location.latitude,
              longitude: location.longitude
            };
            this.setData({
              [field]: resolvedPlace,
              [`${field}Keyword`]: resolvedPlace.name,
              [`${field}Results`]: [],
              locatingField: "",
              routePlanResponse: null,
              routePlans: [],
              aiAdvice: null,
              recommendedPlan: null
            });
            this.fillRouteNameFromDestination(field, resolvedPlace);
            wx.showToast({ title: "地点名称已识别" });
          })
          .catch((error) => {
            this.setData({ locatingField: "" });
            wx.showModal({
              title: "地点名称识别失败",
              content: error.message || "请稍后重试，或使用地点搜索。",
              showCancel: false
            });
          });
      },
      fail: (error) => {
        this.setData({ locatingField: "" });
        this.handleLocationFailure(error);
      }
    });
  },

  handleLocationFailure(error) {
    const message = error && error.errMsg || "";
    if (/auth deny|auth denied|authorize:fail/.test(message)) {
      wx.showModal({
        title: "需要位置权限",
        content: "请在微信设置中允许使用位置，然后再点“使用当前位置”。",
        confirmText: "去设置",
        success: ({ confirm }) => {
          if (confirm) wx.openSetting();
        }
      });
      return;
    }
    wx.showModal({
      title: "暂时无法定位",
      content: "请确认手机定位已经开启，并尽量到信号较好的位置后重试。",
      showCancel: false
    });
  },

  createRoute() {
    const {
      routeName,
      elderSlot,
      mode,
      origin,
      destination,
      routePlanResponse,
      aiAdvice
    } = this.data;
    if (!routeName.trim() || !origin || !destination) {
      wx.showToast({ title: "请确认路线名称、起点和终点", icon: "none" });
      return;
    }
    if (!routePlanResponse || !aiAdvice) {
      this.prepareAdvice();
      return;
    }
    this.setData({ creating: true });
    createAndSaveRouteDraft({
      id: createRouteId(),
      name: routeName.trim(),
      elderSlot,
      mode,
      origin,
      destination,
      planResponse: routePlanResponse,
      routeIndex: aiAdvice.recommendedPlanIndex
    })
      .then((route) => {
        wx.showToast({ title: "路线草稿已生成" });
        wx.navigateTo({ url: `/pages/route-review/route-review?id=${route.id}` });
      })
      .catch((error) => {
        wx.showModal({
          title: "路线生成失败",
          content: error.message || "请检查路线服务配置后重试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ creating: false }));
  },

  prepareAdvice() {
    const { routeName, mode, origin, destination } = this.data;
    if (!routeName.trim() || !origin || !destination) {
      wx.showToast({ title: "请确认路线名称、起点和终点", icon: "none" });
      return;
    }
    this.setData({
      advising: true,
      routePlanResponse: null,
      routePlans: [],
      aiAdvice: null,
      recommendedPlan: null
    });
    prepareRouteAdvice({ mode, origin, destination })
      .then(({ response, plans, advice }) => {
        const displayPlans = plans.map((plan) => ({
          ...plan,
          distanceText: plan.distance >= 1000
            ? `${(plan.distance / 1000).toFixed(1)} 公里`
            : `${plan.distance} 米`,
          durationText: `${Math.max(1, Math.round(plan.duration / 60))} 分钟`
        }));
        this.setData({
          routePlanResponse: response,
          routePlans: displayPlans,
          aiAdvice: advice,
          recommendedPlan: displayPlans.find(
            (plan) => plan.index === advice.recommendedPlanIndex
          ) || displayPlans[0]
        });
        wx.showToast({ title: "路线建议已生成" });
      })
      .catch((error) => {
        wx.showModal({
          title: "路线生成失败",
          content: error.message || "请稍后重试。",
          showCancel: false
        });
      })
      .finally(() => this.setData({ advising: false }));
  },

  openDraft(event) {
    wx.navigateTo({
      url: `/pages/route-review/route-review?id=${event.currentTarget.dataset.id}`
    });
  },

  deleteDraft(event) {
    const routeId = event.currentTarget.dataset.id;
    const route = this.data.drafts.find((item) => item.id === routeId);
    if (!route || !route.canDelete || this.data.deletingRouteId) return;
    wx.showModal({
      title: "删除路线草稿？",
      content: `删除“${route.name}”后无法恢复。`,
      confirmText: "确认删除",
      confirmColor: "#C53F36",
      success: ({ confirm }) => {
        if (!confirm) return;
        this.setData({ deletingRouteId: routeId });
        deleteRouteDraft(routeId)
          .then(() => {
            this.setData({
              drafts: this.data.drafts.filter((item) => item.id !== routeId)
            });
            wx.showToast({ title: "草稿已删除" });
          })
          .catch((error) => {
            wx.showModal({
              title: "删除未完成",
              content: error.message || "请稍后再试。",
              showCancel: false
            });
          })
          .finally(() => this.setData({ deletingRouteId: "" }));
      }
    });
  }
});
