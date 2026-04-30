/**
 * 通用工具函数模块 - 提取自 old_renderer.js
 */

/**
 * 解码 Base64 内容，兼容 URL 安全格式并处理 UTF-8
 */
export function decodeBase64Content(str) {
    try {
        str = str.replace(/-/g, '+').replace(/_/g, '/');
        return decodeURIComponent(atob(str).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
    } catch (e) { 
        try {
            return atob(str); 
        } catch (err) {
            return str;
        }
    }
}

/**
 * 从代理链接中提取备注 (ps 字段或 # 后缀)
 */
export function getProxyRemark(link) {
    if (!link) return '';
    link = link.trim();
    try {
        if (link.startsWith('vmess://')) {
            const base64Str = link.replace('vmess://', '');
            const configStr = decodeBase64Content(base64Str);
            try { return JSON.parse(configStr).ps || ''; } catch (e) { return ''; }
        } else if (link.includes('#')) {
            return decodeURIComponent(link.split('#')[1]).trim();
        }
    } catch (e) { }
    return '';
}

/**
 * 简单的文本转颜色生成器
 */
export function stringToColor(str) {
    if (!str) return '#cccccc';
    let hash = 0;
    for (let i = 0; i < str.length; i++) hash = str.charCodeAt(i) + ((hash << 5) - hash);
    const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
    return '#' + "00000".substring(0, 6 - c.length) + c;
}

/**
 * 简易 Markdown 解析器，用于版本更新日志
 */
export function parseMarkdown(md) {
    if (!md) return '';
    return md
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') // 转义 HTML
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>') // 加粗
        .replace(/\*(.*?)\*/g, '<em>$1</em>') // 斜体
        .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="#" onclick="window.electronAPI.invoke(\'open-url\', \'$2\'); return false;" style="color:var(--accent);text-decoration:none;">$1</a>') // 链接
        .replace(/^\s*-\s+(.*)$/gm, '<li>$1</li>') // 列表项
        .replace(/(<li>.*<\/li>)/s, '<ul style="padding-left: 20px; margin: 5px 0;">$1</ul>') // 包装列表
        .replace(/\n\n/g, '<br><br>') // 段落
        .replace(/\n/g, '<br>'); // 换行
}

/**
 * 生成 UUID v4
 */
export function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}
