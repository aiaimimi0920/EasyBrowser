<template>
    <!-- 密码输入模态框 -->
    <div id="passwordModal" class="modal-overlay" :class="{ active: uiStore.passwordModalVisible }" style="z-index: 2400;">
        <div class="modal-content" style="width: 380px;">
            <div class="modal-header">
                <span>{{ uiStore.passwordTitle }}</span>
                <span style="cursor:pointer" @click="uiStore.passwordModalVisible = false">✕</span>
            </div>
            <div class="modal-body">
                <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 15px;">
                    {{ $t('passwordHint') || '完整备份包含敏感数据（Cookie、密码等），将使用 AES-256 加密保护。' }}
                </p>
                <label style="font-size: 12px;">{{ $t('password') || '密码' }}</label>
                <input type="password" v-model="uiStore.passwordValue" :placeholder="$t('inputPassword') || '请输入密码'" style="margin-bottom: 10px;" @keyup.enter="uiStore.submitPassword">
                
                <template v-if="uiStore.passwordShowConfirm">
                    <label style="font-size: 12px;">{{ $t('confirmPassword') || '确认密码' }}</label>
                    <input type="password" v-model="uiStore.passwordConfirmValue" :placeholder="$t('inputPasswordAgain') || '请再次输入密码'" @keyup.enter="uiStore.submitPassword">
                </template>
            </div>
            <div class="modal-footer" style="display: flex; justify-content: flex-end; gap: 10px;">
                <button class="outline" @click="uiStore.passwordModalVisible = false">{{ $t('cancel') || '取消' }}</button>
                <button @click="uiStore.submitPassword">{{ $t('ok') || '确定' }}</button>
            </div>
        </div>
    </div>
</template>

<script setup>
import { useUIStore } from '../store/useUIStore';
const uiStore = useUIStore();
</script>
