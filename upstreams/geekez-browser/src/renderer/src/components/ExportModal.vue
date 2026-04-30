<template>
    <div id="exportModal" class="modal-overlay" style="z-index: 2200;" @mousedown.self="uiStore.closeExportModal()">
        <div class="modal-content">
            <div class="modal-header">
                <span>{{ t('exportTitle') }}</span>
                <span style="cursor:pointer" @click="uiStore.closeExportModal()">✕</span>
            </div>
            <div class="export-option" @click="uiStore.openExportSelectModal('full-backup')">
                <div>
                    <div class="export-title" style="color: var(--accent);">{{ t('expFullBackup') || '🔐 完整备份（全部）' }}</div>
                    <div class="export-desc">{{ t('expFullBackupDesc') || '含浏览器数据（Cookie/密码/书签），AES-256加密' }}</div>
                </div><span>🔒</span>
            </div>
            <div class="export-option" @click="uiStore.openExportSelectModal('all')">
                <div>
                    <div class="export-title">{{ t('expAllProfiles') || '完整备份（指纹环境）' }}</div>
                    <div class="export-desc">{{ t('expAllProfilesDesc') || '导出指纹配置 + 前置代理（不含浏览器数据）' }}</div>
                </div><span>📦</span>
            </div>
            <div class="export-option" @click="uiStore.openExportSelectModal('proxies')">
                <div>
                    <div class="export-title">{{ t('expProxies') || '前置代理' }}</div>
                    <div class="export-desc">{{ t('expProxiesDesc') || '导出手动节点和订阅配置' }}</div>
                </div><span>🔗</span>
            </div>
            <div class="export-option" @click="uiStore.openExportSelectModal('profiles')">
                <div>
                    <div class="export-title">{{ t('expProfiles') || '指纹环境' }}</div>
                    <div class="export-desc">{{ t('expProfilesDesc') || '仅导出环境指纹配置' }}</div>
                </div><span>👤</span>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';

const uiStore = useUIStore();
const t = window.t || ((key) => key);
</script>
