import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ipcService } from '../services/ipc.service';

export const useUIStore = defineStore('ui', () => {
    // Modal visibility states
    const addModalVisible = ref(false);
    const editModalVisible = ref(false);
    const proxyModalVisible = ref(false);
    const exportModalVisible = ref(false);
    const settingsModalVisible = ref(false);
    const helpModalVisible = ref(false);
    const alertModalVisible = ref(false);
    const confirmModalVisible = ref(false);
    const inputModalVisible = ref(false);
    const subEditModalVisible = ref(false);
    const editProxyNodeModalVisible = ref(false);
    const passwordModalVisible = ref(false);
    const batchAddProxyModalVisible = ref(false);
    const exportSelectModalVisible = ref(false);
    const exportType = ref('all');
    
    // UI Theme & Lang
    const theme = ref(localStorage.getItem('geekez_theme') || 'geek');
    const lang = ref(localStorage.getItem('geekez_lang') || 'cn');

    // Dialog messages
    const alertMsg = ref('');
    const alertShowBtn = ref(true);
    const confirmMsg = ref('');
    const confirmNotes = ref('');
    const inputModalTitle = ref('');
    const inputModalValue = ref('');
    
    // Password Modal
    const passwordTitle = ref('');
    const passwordValue = ref('');
    const passwordConfirmValue = ref('');
    const passwordShowConfirm = ref(false);
    const passwordResolve = ref(null);

    const progressModalVisible = ref(false);
    const progressPercent = ref(0);
    const progressMessage = ref('');
    const progressTitle = ref('');
    const progressWarn = ref('');
    
    // Callbacks for legacy/store logic
    let confirmCallback = null;
    let inputCallback = null;
    let passwordCallback = null;

    // Active ID for editing
    const currentEditId = ref(null);
    const currentSubEdit = ref(null);

    // Actions
    const openAddModal = () => { 
        console.log('[UIStore] openAddModal called');
        addModalVisible.value = true; 
    };
    const closeAddModal = () => { addModalVisible.value = false; };

    const openEditModal = (id) => {
        console.log('[UIStore] openEditModal called for ID:', id);
        currentEditId.value = id;
        editModalVisible.value = true;
    };
    const closeEditModal = () => {
        currentEditId.value = null;
        editModalVisible.value = false;
    };

    const openExportModal = () => { exportModalVisible.value = true; };
    const closeExportModal = () => { exportModalVisible.value = false; };
    
    const openExportSelectModal = (type) => {
        exportType.value = type;
        exportSelectModalVisible.value = true;
        exportModalVisible.value = false;
    };
    const closeExportSelectModal = () => { exportSelectModalVisible.value = false; };

    const openProxyManager = () => { proxyModalVisible.value = true; };
    const closeProxyManager = () => { proxyModalVisible.value = false; };

    const openSettings = () => { settingsModalVisible.value = true; };
    const closeSettings = () => { settingsModalVisible.value = false; };

    const setTheme = (newTheme) => {
        theme.value = newTheme;
        document.body.setAttribute('data-theme', newTheme);
        localStorage.setItem('geekez_theme', newTheme);
        
        const themeColors = {
            'geek': { bg: '#1e1e2d', symbol: '#ffffff' },
            'light': { bg: '#f0f2f5', symbol: '#000000' },
            'dark': { bg: '#121212', symbol: '#ffffff' }
        };
        const colors = themeColors[newTheme] || themeColors['geek'];
        ipcService.setTitleBarColor(colors);
    };

    const toggleLang = () => {
        const newLang = lang.value === 'cn' ? 'en' : 'cn';
        lang.value = newLang;
        localStorage.setItem('geekez_lang', newLang);
        location.reload();
    };

    // Dialog Actions
    const showAlert = (msg, showBtn = true) => {
        alertMsg.value = msg;
        alertShowBtn.value = showBtn;
        alertModalVisible.value = true;
    };

    const showConfirm = (msg, callback, notes = '') => {
        confirmMsg.value = msg;
        confirmNotes.value = notes;
        confirmCallback = callback;
        confirmModalVisible.value = true;
    };

    const handleConfirm = (result) => {
        confirmModalVisible.value = false;
        if (result && confirmCallback) confirmCallback();
        confirmCallback = null;
    };

    const showInput = (title, callback) => {
        inputModalTitle.value = title;
        inputModalValue.value = '';
        inputCallback = callback;
        inputModalVisible.value = true;
    };

    const submitInput = () => {
        const val = inputModalValue.value.trim();
        if (val && inputCallback) inputCallback(val);
        inputModalVisible.value = false;
        inputCallback = null;
    };

    const openPasswordModal = (title, showConfirm = true, callback = null) => {
        passwordTitle.value = title;
        passwordValue.value = '';
        passwordConfirmValue.value = '';
        passwordShowConfirm.value = showConfirm;
        passwordCallback = callback;
        passwordModalVisible.value = true;
    };

    const submitPassword = () => {
        if (passwordShowConfirm.value && passwordValue.value !== passwordConfirmValue.value) {
            showAlert(window.t ? window.t('passwordMismatch') : 'Passwords do not match');
            return;
        }
        if (passwordCallback) passwordCallback(passwordValue.value);
        passwordModalVisible.value = false;
        passwordCallback = null;
    };

    return {
        addModalVisible,
        editModalVisible,
        proxyModalVisible,
        exportModalVisible,
        settingsModalVisible,
        helpModalVisible,
        alertModalVisible,
        confirmModalVisible,
        inputModalVisible,
        subEditModalVisible,
        editProxyNodeModalVisible,
        passwordModalVisible,
        batchAddProxyModalVisible,
        exportSelectModalVisible,
        exportType,
        theme,
        lang,
        alertMsg,
        alertShowBtn,
        confirmMsg,
        confirmNotes,
        inputModalTitle,
        inputModalValue,
        currentEditId,
        currentSubEdit,
        openAddModal,
        closeAddModal,
        openEditModal,
        closeEditModal,
        openExportModal,
        closeExportModal,
        openExportSelectModal,
        closeExportSelectModal,
        openProxyManager,
        closeProxyManager,
        openSettings,
        closeSettings,
        setTheme,
        toggleLang,
        showAlert,
        showConfirm,
        handleConfirm,
        showInput,
        submitInput,
        passwordTitle,
        passwordValue,
        passwordConfirmValue,
        passwordShowConfirm,
        progressModalVisible,
        progressPercent,
        progressMessage,
        progressTitle,
        progressWarn,
        batchAddProxyModalVisible,
        openPasswordModal,
        submitPassword
    };
});
