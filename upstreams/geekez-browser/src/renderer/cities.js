// Major Cities for Geolocation Selector
const CITY_DATA = [
    // --- North America ---
    { name: "America/New_York", lat: 40.7128, lng: -74.0060 },
    { name: "America/Los_Angeles", lat: 34.0522, lng: -118.2437 },
    { name: "America/Chicago", lat: 41.8781, lng: -87.6298 },
    { name: "America/Houston", lat: 29.7604, lng: -95.3698 },
    { name: "America/Phoenix", lat: 33.4484, lng: -112.0740 },
    { name: "America/Philadelphia", lat: 39.9526, lng: -75.1652 },
    { name: "America/San_Antonio", lat: 29.4241, lng: -98.4936 },
    { name: "America/San_Diego", lat: 32.7157, lng: -117.1611 },
    { name: "America/Dallas", lat: 32.7767, lng: -96.7970 },
    { name: "America/San_Jose", lat: 37.3382, lng: -121.8863 },
    { name: "America/Austin", lat: 30.2672, lng: -97.7431 },
    { name: "America/San_Francisco", lat: 37.7749, lng: -122.4194 },
    { name: "America/Seattle", lat: 47.6062, lng: -122.3321 },
    { name: "America/Washington_DC", lat: 38.9072, lng: -77.0369 },
    { name: "America/Boston", lat: 42.3601, lng: -71.0589 },
    { name: "America/Miami", lat: 25.7617, lng: -80.1918 },
    { name: "America/Toronto", lat: 43.6510, lng: -79.3470 },
    { name: "America/Vancouver", lat: 49.2827, lng: -123.1207 },
    { name: "America/Montreal", lat: 45.5017, lng: -73.5673 },
    { name: "America/Mexico_City", lat: 19.4326, lng: -99.1332 },
    { name: "America/Sao_Paulo", lat: -23.5505, lng: -46.6333 },

    // --- Europe ---
    { name: "Europe/London", lat: 51.5074, lng: -0.1278 },
    { name: "Europe/Birmingham", lat: 52.4862, lng: -1.8904 },
    { name: "Europe/Manchester", lat: 53.4808, lng: -2.2426 },
    { name: "Europe/Paris", lat: 48.8566, lng: 2.3522 },
    { name: "Europe/Marseille", lat: 43.2965, lng: 5.3698 },
    { name: "Europe/Berlin", lat: 52.5200, lng: 13.4050 },
    { name: "Europe/Munich", lat: 48.1351, lng: 11.5820 },
    { name: "Europe/Frankfurt", lat: 50.1109, lng: 8.6821 },
    { name: "Europe/Rome", lat: 41.9028, lng: 12.4964 },
    { name: "Europe/Milan", lat: 45.4642, lng: 9.1900 },
    { name: "Europe/Madrid", lat: 40.4168, lng: -3.7038 },
    { name: "Europe/Barcelona", lat: 41.3851, lng: 2.1734 },
    { name: "Europe/Amsterdam", lat: 52.3676, lng: 4.9041 },
    { name: "Europe/Brussels", lat: 50.8503, lng: 4.3517 },
    { name: "Europe/Zurich", lat: 47.3769, lng: 8.5417 },
    { name: "Europe/Vienna", lat: 48.2082, lng: 16.3738 },
    { name: "Europe/Moscow", lat: 55.7558, lng: 37.6173 },
    { name: "Europe/Istanbul", lat: 41.0082, lng: 28.9784 },

    // --- Asia ---
    { name: "Asia/Tokyo", lat: 35.6762, lng: 139.6503 },
    { name: "Asia/Osaka", lat: 34.6937, lng: 135.5023 },
    { name: "Asia/Kyoto", lat: 35.0116, lng: 135.7681 },
    { name: "Asia/Singapore", lat: 1.3521, lng: 103.8198 },
    { name: "Asia/Hong_Kong", lat: 22.3193, lng: 114.1694 },
    { name: "Asia/Beijing", lat: 39.9042, lng: 116.4074 },
    { name: "Asia/Shanghai", lat: 31.2304, lng: 121.4737 },
    { name: "Asia/Taipei", lat: 25.0330, lng: 121.5654 },
    { name: "Asia/Seoul", lat: 37.5665, lng: 126.9780 },
    { name: "Asia/Dubai", lat: 25.2048, lng: 55.2708 },
    { name: "Asia/Mumbai", lat: 19.0760, lng: 72.8777 },
    { name: "Asia/Bangkok", lat: 13.7563, lng: 100.5018 },
    { name: "Asia/Jakarta", lat: -6.2088, lng: 106.8456 },
    { name: "Asia/Ho_Chi_Minh", lat: 10.8231, lng: 106.6297 },

    // --- Australia & Pacific ---
    { name: "Australia/Sydney", lat: -33.8688, lng: 151.2093 },
    { name: "Australia/Melbourne", lat: -37.8136, lng: 144.9631 }
];

if (typeof window !== "undefined") window.CITY_DATA = CITY_DATA;
if (typeof module !== "undefined") module.exports = CITY_DATA;
