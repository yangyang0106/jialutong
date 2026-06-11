const { uploadUrl, uploadToken } = require("../config/upload");
const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_AUDIO_BYTES = 5 * 1024 * 1024;

function saveLocalFile(tempFilePath) {
  return new Promise((resolve, reject) => {
    wx.saveFile({
      tempFilePath,
      success: ({ savedFilePath }) => resolve(savedFilePath),
      fail: reject
    });
  });
}

function uploadFile(tempFilePath, metadata) {
  if (!/^https:\/\//.test(uploadUrl)) {
    return Promise.reject(new Error("上传地址必须使用 HTTPS"));
  }
  if (!metadata.routeId || !metadata.stepNo || !["image", "audio"].includes(metadata.kind)) {
    return Promise.reject(new Error("上传参数不完整"));
  }
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: uploadUrl,
      filePath: tempFilePath,
      name: "file",
      header: uploadToken ? { Authorization: `Bearer ${uploadToken}` } : {},
      formData: metadata,
      success: ({ statusCode, data }) => {
        if (statusCode < 200 || statusCode >= 300) {
          reject(new Error(`上传失败：${statusCode}`));
          return;
        }
        try {
          const response = JSON.parse(data);
          if (!response.url) {
            reject(new Error("上传接口未返回 url"));
            return;
          }
          resolve(response.url);
        } catch (error) {
          reject(error);
        }
      },
      fail: reject
    });
  });
}

function validateFileSize(size, kind) {
  const limit = kind === "image" ? MAX_IMAGE_BYTES : MAX_AUDIO_BYTES;
  if (size && size > limit) {
    return Promise.reject(new Error(kind === "image" ? "图片不能超过 10MB" : "语音不能超过 5MB"));
  }
  return Promise.resolve();
}

function storeFile(tempFilePath, metadata, size) {
  return validateFileSize(size, metadata.kind).then(() => {
    if (uploadUrl) {
      return uploadFile(tempFilePath, metadata);
    }
    return saveLocalFile(tempFilePath);
  });
}

function removeStoredFile(filePath) {
  if (!filePath || /^https?:\/\//.test(filePath)) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    wx.removeSavedFile({
      filePath,
      complete: resolve
    });
  });
}

module.exports = {
  storeFile,
  removeStoredFile
};
