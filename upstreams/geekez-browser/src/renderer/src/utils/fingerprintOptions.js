function makeOption(value, label, labelZh = '') {
    return { value, label, labelZh: labelZh || label };
}

export const browserTypeOptions = [
    makeOption('auto', 'Auto Random', '自动随机'),
    makeOption('chrome', 'Google Chrome', 'Google Chrome'),
    makeOption('edge', 'Microsoft Edge', 'Microsoft Edge')
];

export const browserMajorVersionOptions = [
    makeOption('auto', 'Auto Random', '自动随机'),
    ...Array.from({ length: 19 }, (_, i) => {
        const major = 147 - i;
        return makeOption(major, `v${major}`, `v${major}`);
    })
];

export const browserVersionPresetOptions = [
    makeOption('none', 'No UA Modification', '不修改 UA'),
    makeOption('auto', 'Auto Random', '自动随机'),
    ...Array.from({ length: 19 }, (_, i) => {
        const major = 147 - i;
        return [
            makeOption(`chrome:${major}`, `Chrome v${major}`, `Chrome v${major}`),
            makeOption(`edge:${major}`, `Edge v${major}`, `Edge v${major}`)
        ];
    }).flat()
];

export const tlsClientHelloOptions = [
    makeOption('auto', 'Auto (Map by Browser Version)', '自动（按浏览器版本映射）'),
    makeOption('chrome', 'Chrome uTLS', 'Chrome 指纹'),
    makeOption('edge', 'Edge uTLS', 'Edge 指纹'),
    makeOption('firefox', 'Firefox uTLS', 'Firefox 指纹'),
    makeOption('safari', 'Safari uTLS', 'Safari 指纹'),
    makeOption('ios', 'iOS Safari uTLS', 'iOS Safari 指纹'),
    makeOption('android', 'Android uTLS', 'Android 指纹'),
    makeOption('qq', 'QQ uTLS', 'QQ 指纹'),
    makeOption('360', '360 uTLS', '360 指纹'),
    makeOption('random', 'Random uTLS', '随机指纹'),
    makeOption('randomized', 'Randomized uTLS', '随机化指纹'),
    makeOption('hellorandomizednoalpn', 'Randomized (No ALPN)', '随机化（无 ALPN）')
];

export const webglProfileOptions = [
    makeOption('none', 'No WebGL Modification', '不修改 WebGL'),
    makeOption('auto', 'Auto Random', '自动随机'),

    makeOption('win_intel_uhd_620', 'Windows - Intel UHD 620', 'Windows - Intel UHD 620'),
    makeOption('win_intel_uhd_630', 'Windows - Intel UHD 630', 'Windows - Intel UHD 630'),
    makeOption('win_intel_iris_xe', 'Windows - Intel Iris Xe', 'Windows - Intel Iris Xe'),
    makeOption('win_nvidia_gtx_1050', 'Windows - NVIDIA GTX 1050', 'Windows - NVIDIA GTX 1050'),
    makeOption('win_nvidia_gtx_1060', 'Windows - NVIDIA GTX 1060', 'Windows - NVIDIA GTX 1060'),
    makeOption('win_nvidia_gtx_1660', 'Windows - NVIDIA GTX 1660 SUPER', 'Windows - NVIDIA GTX 1660 SUPER'),
    makeOption('win_nvidia_1650', 'Windows - NVIDIA GTX 1650', 'Windows - NVIDIA GTX 1650'),
    makeOption('win_nvidia_rtx_2060', 'Windows - NVIDIA RTX 2060', 'Windows - NVIDIA RTX 2060'),
    makeOption('win_nvidia_rtx_3060', 'Windows - NVIDIA RTX 3060', 'Windows - NVIDIA RTX 3060'),
    makeOption('win_nvidia_rtx_3070', 'Windows - NVIDIA RTX 3070', 'Windows - NVIDIA RTX 3070'),
    makeOption('win_nvidia_rtx_3080', 'Windows - NVIDIA RTX 3080', 'Windows - NVIDIA RTX 3080'),
    makeOption('win_nvidia_rtx_4060', 'Windows - NVIDIA RTX 4060', 'Windows - NVIDIA RTX 4060'),
    makeOption('win_nvidia_rtx_4070', 'Windows - NVIDIA RTX 4070', 'Windows - NVIDIA RTX 4070'),
    makeOption('win_nvidia_rtx_4080', 'Windows - NVIDIA RTX 4080', 'Windows - NVIDIA RTX 4080'),
    makeOption('win_amd_rx_580', 'Windows - AMD RX 580', 'Windows - AMD RX 580'),
    makeOption('win_amd_rx_6600', 'Windows - AMD RX 6600 XT', 'Windows - AMD RX 6600 XT'),
    makeOption('win_amd_rx_6700', 'Windows - AMD RX 6700 XT', 'Windows - AMD RX 6700 XT'),
    makeOption('win_amd_rx_6800', 'Windows - AMD RX 6800 XT', 'Windows - AMD RX 6800 XT'),
    makeOption('win_amd_vega_8', 'Windows - AMD Vega 8', 'Windows - AMD Vega 8'),
    makeOption('win_amd_rx6600', 'Windows - AMD RX 6600 XT (Legacy)', 'Windows - AMD RX 6600 XT（兼容）'),

    makeOption('mac_apple_m1', 'macOS - Apple M1', 'macOS - Apple M1'),
    makeOption('mac_apple_m2', 'macOS - Apple M2', 'macOS - Apple M2'),
    makeOption('mac_apple_m3', 'macOS - Apple M3', 'macOS - Apple M3'),
    makeOption('mac_apple_m4', 'macOS - Apple M4', 'macOS - Apple M4'),
    makeOption('mac_intel_iris', 'macOS - Intel Iris', 'macOS - Intel Iris'),
    makeOption('mac_intel_uhd_630', 'macOS - Intel UHD 630', 'macOS - Intel UHD 630'),
    makeOption('mac_amd_pro_560x', 'macOS - AMD Pro 560X', 'macOS - AMD Pro 560X'),
    makeOption('mac_amd_pro_5500m', 'macOS - AMD Pro 5500M', 'macOS - AMD Pro 5500M'),

    makeOption('linux_mesa_intel_620', 'Linux - Mesa Intel UHD 620', 'Linux - Mesa Intel UHD 620'),
    makeOption('linux_mesa_intel_xe', 'Linux - Mesa Intel Xe', 'Linux - Mesa Intel Xe'),
    makeOption('linux_nvidia_1650', 'Linux - NVIDIA GTX 1650', 'Linux - NVIDIA GTX 1650'),
    makeOption('linux_nvidia_3060', 'Linux - NVIDIA RTX 3060', 'Linux - NVIDIA RTX 3060'),
    makeOption('linux_nvidia_4090', 'Linux - NVIDIA RTX 4090', 'Linux - NVIDIA RTX 4090'),
    makeOption('linux_mesa_amd_6600', 'Linux - Mesa AMD RX 6600 XT', 'Linux - Mesa AMD RX 6600 XT'),
    makeOption('linux_mesa_amd_6800', 'Linux - Mesa AMD RX 6800 XT', 'Linux - Mesa AMD RX 6800 XT'),
    makeOption('linux_mesa_amd', 'Linux - Mesa AMD RX 6600 XT (Legacy)', 'Linux - Mesa AMD RX 6600 XT（兼容）'),
    makeOption('linux_mesa_intel', 'Linux - Mesa Intel UHD 620 (Legacy)', 'Linux - Mesa Intel UHD 620（兼容）')
];

export function getOptionLabel(option) {
    if (!option) return '';
    if (window.curLang === 'cn') return option.labelZh || option.label;
    return option.label;
}
