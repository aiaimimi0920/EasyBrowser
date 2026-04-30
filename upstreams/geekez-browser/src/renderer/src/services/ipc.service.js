/**
 * IPC 服务基座 - 封装底层 window.electronAPI
 * 提供标准化的 Promise 接口与统一的错误处理
 */

export const ipcService = {
    /**
     * 调用 IPC 接口 (异步等待结果)
     */
    async invoke(channel, ...args) {
        try {
            if (!window.electronAPI || !window.electronAPI.invoke) {
                console.warn(`[IPC Service] window.electronAPI.invoke not ready for channel: ${channel}`);
                return null;
            }
            return await window.electronAPI.invoke(channel, ...args);
        } catch (error) {
            console.error(`[IPC Service] Error calling ${channel}:`, error);
            throw error;
        }
    },

    /**
     * 发送单向 IPC 消息
     */
    send(channel, ...args) {
        try {
            if (!window.electronAPI || !window.electronAPI.send) {
                console.warn(`[IPC Service] window.electronAPI.send not ready for channel: ${channel}`);
                return;
            }
            window.electronAPI.send(channel, ...args);
        } catch (error) {
            console.error(`[IPC Service] Error sending to ${channel}:`, error);
        }
    },

    /**
     * 监听 IPC 事件
     */
    on(channel, callback) {
        if (window.electronAPI && window.electronAPI.on) {
            window.electronAPI.on(channel, callback);
        } else {
            console.warn(`[IPC Service] window.electronAPI.on is not available for channel: ${channel}`);
        }
    },

    /**
     * 获取设置同步接口
     */
    async getSettings() {
        return await this.invoke('get-settings');
    },

    /**
     * 保存设置同步接口
     */
    async saveSettings(settings) {
        const payload = settings && typeof settings === 'object'
            ? JSON.parse(JSON.stringify(settings))
            : settings;
        return await this.invoke('save-settings', payload);
    },

    /**
     * 设置标题栏颜色 (Mac/Win)
     */
    setTitleBarColor(colors) {
        this.invoke('set-title-bar-color', colors);
    },

    /**
     * 唤起外部浏览器打开 URL
     */
    openUrl(url) {
        this.invoke('open-url', url);
    },

    /**
     * 获取 App 元数据 (版本、名称等)
     */
    async getAppInfo() {
        return await this.invoke('get-app-info');
    }
};
