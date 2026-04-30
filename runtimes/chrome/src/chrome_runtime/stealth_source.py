from __future__ import annotations

import json
from typing import Any


def build_stealth_source(profile: dict[str, Any]) -> str:
    script = r'''
(() => {
  const config = __CONFIG_JSON__;
  if (globalThis.__codexStealthApplied) {
    return;
  }
  try {
    Object.defineProperty(globalThis, '__codexStealthApplied', { value: true, configurable: false });
  } catch (error) {
    globalThis.__codexStealthApplied = true;
  }

  const navProto = Object.getPrototypeOf(navigator);

  const safeDefineProperty = (obj, prop, descriptor) => {
    try {
      Object.defineProperty(obj, prop, descriptor);
    } catch (error) {
      if (descriptor && Object.prototype.hasOwnProperty.call(descriptor, 'value')) {
        try {
          obj[prop] = descriptor.value;
        } catch (assignError) {}
      }
    }
  };

  const safeDefineGetter = (obj, prop, getter) => {
    safeDefineProperty(obj, prop, {
      configurable: true,
      enumerable: true,
      get: getter,
    });
  };

  const safeDefineValue = (obj, prop, value, configurable = true, enumerable = true, writable = true) => {
    safeDefineProperty(obj, prop, {
      configurable,
      enumerable,
      writable,
      value,
    });
  };

  const nativeToString = Function.prototype.toString;
  const nativeToStringMap = new WeakMap();
  const markAsNative = (fn, name) => {
    if (typeof fn !== 'function') {
      return fn;
    }
    try {
      const displayName = String(name || fn.name || '').trim();
      nativeToStringMap.set(fn, displayName ? `function ${displayName}() { [native code] }` : 'function () { [native code] }');
    } catch (error) {}
    return fn;
  };

  if (!nativeToString.__codexStealthWrapped) {
    const wrappedToString = markAsNative(function toString() {
      if (nativeToStringMap.has(this)) {
        return nativeToStringMap.get(this);
      }
      return nativeToString.call(this);
    }, 'toString');
    safeDefineValue(wrappedToString, '__codexStealthWrapped', true, false, false, false);
    safeDefineValue(Function.prototype, 'toString', wrappedToString);
  }

  const createMagicArray = (items, protoCtorName, tagName, keyField) => {
    const ctor = globalThis[protoCtorName];
    const proto = ctor && ctor.prototype ? ctor.prototype : Object.prototype;
    const arr = Object.create(proto);
    safeDefineValue(arr, Symbol.toStringTag, tagName, true, false, false);
    items.forEach((item, index) => {
      safeDefineProperty(arr, index, {
        configurable: true,
        enumerable: false,
        writable: false,
        value: item,
      });
      if (item && item[keyField]) {
        safeDefineProperty(arr, item[keyField], {
          configurable: true,
          enumerable: false,
          writable: false,
          value: item,
        });
      }
    });
    safeDefineProperty(arr, 'length', {
      configurable: true,
      enumerable: false,
      get: () => items.length,
    });
    safeDefineValue(arr, 'item', markAsNative(function item(index) {
      const numeric = Number(index);
      return Number.isFinite(numeric) ? (arr[numeric] || null) : null;
    }, 'item'), true, false, false);
    safeDefineValue(arr, 'namedItem', markAsNative(function namedItem(name) {
      return arr[String(name)] || null;
    }, 'namedItem'), true, false, false);
    return arr;
  };

  const createMimeType = (data) => {
    const proto = globalThis.MimeType && MimeType.prototype ? MimeType.prototype : Object.prototype;
    const mimeType = Object.create(proto);
    safeDefineValue(mimeType, Symbol.toStringTag, 'MimeType', true, false, false);
    safeDefineValue(mimeType, 'type', String(data.type || ''), true, false, false);
    safeDefineValue(mimeType, 'suffixes', String(data.suffixes || ''), true, false, false);
    safeDefineValue(mimeType, 'description', String(data.description || ''), true, false, false);
    return mimeType;
  };

  const createPlugin = (data) => {
    const proto = globalThis.Plugin && Plugin.prototype ? Plugin.prototype : Object.prototype;
    const plugin = Object.create(proto);
    safeDefineValue(plugin, Symbol.toStringTag, 'Plugin', true, false, false);
    safeDefineValue(plugin, 'name', String(data.name || ''), true, false, false);
    safeDefineValue(plugin, 'filename', String(data.filename || ''), true, false, false);
    safeDefineValue(plugin, 'description', String(data.description || ''), true, false, false);
    return plugin;
  };

  try {
    try {
      if ('webdriver' in navProto) {
        delete navProto.webdriver;
      }
    } catch (innerError) {}
    safeDefineGetter(navProto, 'webdriver', () => undefined);
  } catch (error) {}

  try {
    safeDefineGetter(navProto, 'userAgent', () => config.userAgent);
    safeDefineGetter(navProto, 'appVersion', () => config.userAgent.replace(/^Mozilla\/5\.0\s*/, ''));
    safeDefineGetter(navProto, 'platform', () => config.platformShort);
    safeDefineGetter(navProto, 'vendor', () => config.vendor);
    safeDefineGetter(navProto, 'languages', () => Object.freeze(config.languages.slice()));
    safeDefineGetter(navProto, 'language', () => config.languages[0]);
    safeDefineGetter(navProto, 'hardwareConcurrency', () => config.hardwareConcurrency);
  } catch (error) {}

  try {
    if (!navigator.userAgentData) {
      const userAgentData = {
        brands: config.brands,
        mobile: !!config.mobile,
        platform: config.platformName,
        getHighEntropyValues: async (hints) => {
          const data = {
            architecture: config.architecture,
            brands: config.brands,
            fullVersionList: config.fullVersionList,
            mobile: !!config.mobile,
            model: config.model,
            platform: config.platformName,
            platformVersion: config.platformVersion,
            uaFullVersion: config.fullVersion,
            wow64: false,
          };
          const requested = {};
          for (const hint of hints || []) {
            if (hint in data) {
              requested[hint] = data[hint];
            }
          }
          requested.brands = data.brands;
          requested.mobile = data.mobile;
          requested.platform = data.platform;
          return requested;
        },
        toJSON() {
          return { brands: this.brands, mobile: this.mobile, platform: this.platform };
        },
      };
      safeDefineGetter(navProto, 'userAgentData', () => userAgentData);
    }
  } catch (error) {}

  try {
    const isSecure = String(document.location.protocol || '').startsWith('https');
    if (globalThis.Notification && isSecure) {
      safeDefineGetter(Notification, 'permission', () => 'default');
    }
    const permissionProto = globalThis.Permissions && globalThis.Permissions.prototype;
    if (permissionProto && permissionProto.query && !permissionProto.query.__codexStealthWrapped) {
      const originalQuery = permissionProto.query;
      const wrappedQuery = function(parameters) {
        if (parameters && parameters.name === 'notifications') {
          const state = globalThis.Notification && Notification.permission ? Notification.permission : 'default';
          const status = {
            state: state === 'default' ? (isSecure ? 'default' : 'prompt') : state,
            onchange: null,
          };
          const statusProto = globalThis.PermissionStatus && PermissionStatus.prototype ? PermissionStatus.prototype : Object.prototype;
          return Promise.resolve(Object.setPrototypeOf(status, statusProto));
        }
        return originalQuery.apply(this, arguments);
      };
      markAsNative(wrappedQuery, 'query');
      wrappedQuery.__codexStealthWrapped = true;
      safeDefineValue(permissionProto, 'query', wrappedQuery);
    }
  } catch (error) {}

  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        writable: true,
        enumerable: true,
        configurable: false,
        value: {},
      });
    }
    if (!('app' in window.chrome)) {
      window.chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
        getDetails() { return null; },
        getIsInstalled() { return false; },
        runningState() { return 'cannot_run'; },
      };
    }
    if (!('csi' in window.chrome) && window.performance && window.performance.timing) {
      window.chrome.csi = function() {
        const timing = window.performance.timing;
        return {
          onloadT: timing.domContentLoadedEventEnd,
          startE: timing.navigationStart,
          pageT: Date.now() - timing.navigationStart,
          tran: 15,
        };
      };
      markAsNative(window.chrome.csi, 'csi');
    }
    if (!('loadTimes' in window.chrome) && window.performance) {
      window.chrome.loadTimes = function() {
        const timing = window.performance.timing || {};
        const navEntry = (window.performance.getEntriesByType && window.performance.getEntriesByType('navigation')[0]) || {
          nextHopProtocol: 'h2',
          type: 'other',
        };
        return {
          connectionInfo: navEntry.nextHopProtocol || 'h2',
          npnNegotiatedProtocol: ['h2', 'hq'].includes(navEntry.nextHopProtocol) ? navEntry.nextHopProtocol : 'unknown',
          navigationType: navEntry.type || 'other',
          wasAlternateProtocolAvailable: false,
          wasFetchedViaSpdy: ['h2', 'hq'].includes(navEntry.nextHopProtocol),
          wasNpnNegotiated: ['h2', 'hq'].includes(navEntry.nextHopProtocol),
          firstPaintAfterLoadTime: 0,
          requestTime: (timing.navigationStart || Date.now()) / 1000,
          startLoadTime: (timing.navigationStart || Date.now()) / 1000,
          commitLoadTime: (timing.responseStart || Date.now()) / 1000,
          finishDocumentLoadTime: (timing.domContentLoadedEventEnd || Date.now()) / 1000,
          finishLoadTime: (timing.loadEventEnd || Date.now()) / 1000,
          firstPaintTime: ((window.performance.timeOrigin || Date.now()) / 1000),
        };
      };
      markAsNative(window.chrome.loadTimes, 'loadTimes');
    }
    if (!('runtime' in window.chrome) && String(window.location.protocol || '').startsWith('https')) {
      const runtimeStaticData = {
        OnInstalledReason: {
          CHROME_UPDATE: 'chrome_update',
          INSTALL: 'install',
          SHARED_MODULE_UPDATE: 'shared_module_update',
          UPDATE: 'update',
        },
        OnRestartRequiredReason: {
          APP_UPDATE: 'app_update',
          OS_UPDATE: 'os_update',
          PERIODIC: 'periodic',
        },
        PlatformArch: {
          ARM: 'arm',
          ARM64: 'arm64',
          MIPS: 'mips',
          MIPS64: 'mips64',
          X86_32: 'x86-32',
          X86_64: 'x86-64',
        },
        PlatformNaclArch: {
          ARM: 'arm',
          MIPS: 'mips',
          MIPS64: 'mips64',
          X86_32: 'x86-32',
          X86_64: 'x86-64',
        },
        PlatformOs: {
          ANDROID: 'android',
          CROS: 'cros',
          LINUX: 'linux',
          MAC: 'mac',
          OPENBSD: 'openbsd',
          WIN: 'win',
        },
        RequestUpdateCheckStatus: {
          NO_UPDATE: 'no_update',
          THROTTLED: 'throttled',
          UPDATE_AVAILABLE: 'update_available',
        },
      };
      const makeListener = () => ({
        addListener: markAsNative(function addListener() {}, 'addListener'),
        removeListener: markAsNative(function removeListener() {}, 'removeListener'),
        hasListener: markAsNative(function hasListener() { return false; }, 'hasListener'),
        hasListeners: markAsNative(function hasListeners() { return false; }, 'hasListeners'),
        dispatch: markAsNative(function dispatch() {}, 'dispatch'),
      });
      const runtimeConnect = markAsNative(function connect() {
        return {
          name: '',
          sender: undefined,
          disconnect: markAsNative(function disconnect() {}, 'disconnect'),
          onDisconnect: makeListener(),
          onMessage: makeListener(),
          postMessage: markAsNative(function postMessage() {
            throw new Error('Attempting to use a disconnected port object');
          }, 'postMessage'),
        };
      }, 'connect');
      const runtimeSendMessage = markAsNative(function sendMessage() { return undefined; }, 'sendMessage');
      window.chrome.runtime = {
        ...runtimeStaticData,
        get id() { return undefined; },
        connect: runtimeConnect,
        sendMessage: runtimeSendMessage,
      };
    }
  } catch (error) {}

  try {
    if (!navigator.plugins || !navigator.plugins.length) {
      const mimeTypes = [
        createMimeType({ type: 'application/pdf', suffixes: 'pdf', description: '' }),
        createMimeType({ type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format' }),
        createMimeType({ type: 'application/x-nacl', suffixes: '', description: 'Native Client Executable' }),
        createMimeType({ type: 'application/x-pnacl', suffixes: '', description: 'Portable Native Client Executable' }),
      ];
      const plugins = [
        createPlugin({ name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }),
        createPlugin({ name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' }),
        createPlugin({ name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }),
      ];

      const pluginMimeMap = new Map([
        [plugins[0], [mimeTypes[1]]],
        [plugins[1], [mimeTypes[0]]],
        [plugins[2], [mimeTypes[2], mimeTypes[3]]],
      ]);

      plugins.forEach((plugin) => {
        const linkedMimeTypes = pluginMimeMap.get(plugin) || [];
        linkedMimeTypes.forEach((mimeType, index) => {
          safeDefineProperty(plugin, index, {
            configurable: true,
            enumerable: false,
            writable: false,
            value: mimeType,
          });
          safeDefineProperty(plugin, mimeType.type, {
            configurable: true,
            enumerable: false,
            writable: false,
            value: mimeType,
          });
          safeDefineValue(mimeType, 'enabledPlugin', plugin, true, false, false);
        });
        safeDefineProperty(plugin, 'length', {
          configurable: true,
          enumerable: false,
          get: () => linkedMimeTypes.length,
        });
        safeDefineValue(plugin, 'item', markAsNative(function item(index) {
          const numeric = Number(index);
          return Number.isFinite(numeric) ? (plugin[numeric] || null) : null;
        }, 'item'), true, false, false);
        safeDefineValue(plugin, 'namedItem', markAsNative(function namedItem(name) {
          return plugin[String(name)] || null;
        }, 'namedItem'), true, false, false);
      });

      const mimeTypeArray = createMagicArray(mimeTypes, 'MimeTypeArray', 'MimeTypeArray', 'type');
      const pluginArray = createMagicArray(plugins, 'PluginArray', 'PluginArray', 'name');
      safeDefineValue(pluginArray, 'refresh', markAsNative(function refresh() {}, 'refresh'), true, false, false);
      safeDefineGetter(navProto, 'mimeTypes', () => mimeTypeArray);
      safeDefineGetter(navProto, 'plugins', () => pluginArray);
    }
  } catch (error) {}

  try {
    if (!window.outerWidth || !window.outerHeight) {
      const windowFrame = 85;
      safeDefineValue(window, 'outerWidth', window.innerWidth);
      safeDefineValue(window, 'outerHeight', window.innerHeight + windowFrame);
    }
  } catch (error) {}

  try {
    const addContentWindowProxy = (iframe) => {
      if (iframe.contentWindow) {
        return;
      }
      const proxy = new Proxy(window, {
        get(target, key) {
          if (key === 'self') {
            return this;
          }
          if (key === 'frameElement') {
            return iframe;
          }
          if (key === '0') {
            return undefined;
          }
          return Reflect.get(target, key);
        },
      });
      Object.defineProperty(iframe, 'contentWindow', {
        get() { return proxy; },
        set(value) { return value; },
        enumerable: true,
        configurable: false,
      });
    };
    const originalCreateElement = document.createElement.bind(document);
    const wrappedCreateElement = function(tagName) {
      const element = originalCreateElement.apply(this, arguments);
      if (String(tagName || '').toLowerCase() !== 'iframe') {
        return element;
      }
      const originalSrcdoc = element.srcdoc;
      Object.defineProperty(element, 'srcdoc', {
        configurable: true,
        get() { return originalSrcdoc; },
        set(value) {
          addContentWindowProxy(this);
          Object.defineProperty(this, 'srcdoc', {
            configurable: false,
            writable: false,
            value: originalSrcdoc,
          });
          this.setAttribute('srcdoc', value);
        },
      });
      return element;
    };
    if (!wrappedCreateElement.__codexStealthWrapped) {
      markAsNative(wrappedCreateElement, 'createElement');
      wrappedCreateElement.__codexStealthWrapped = true;
      safeDefineValue(document, 'createElement', wrappedCreateElement);
    }
  } catch (error) {}

  try {
    const originalCanPlayType = globalThis.HTMLMediaElement && HTMLMediaElement.prototype && HTMLMediaElement.prototype.canPlayType;
    if (originalCanPlayType && !originalCanPlayType.__codexStealthWrapped) {
      const wrappedCanPlayType = function(value) {
        const input = String(value || '').trim();
        const original = originalCanPlayType.apply(this, arguments);
        if (!input) {
          return original;
        }
        const [mime, codecRaw] = input.split(';');
        const codecs = String(codecRaw || '')
          .replace(/codecs="/i, '')
          .replace(/"/g, '')
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean);
        if (mime === 'video/mp4' && codecs.includes('avc1.42E01E')) {
          return 'probably';
        }
        if (mime === 'audio/x-m4a' && !codecs.length) {
          return 'maybe';
        }
        if (mime === 'audio/aac' && !codecs.length) {
          return 'probably';
        }
        return original;
      };
      markAsNative(wrappedCanPlayType, 'canPlayType');
      wrappedCanPlayType.__codexStealthWrapped = true;
      safeDefineValue(HTMLMediaElement.prototype, 'canPlayType', wrappedCanPlayType);
    }
  } catch (error) {}

  try {
    const patchWebGL = (Ctor) => {
      if (!Ctor || !Ctor.prototype || !Ctor.prototype.getParameter) {
        return;
      }
      const original = Ctor.prototype.getParameter;
      if (original.__codexStealthWrapped) {
        return;
      }
      const wrapped = function(parameter) {
        const result = original.apply(this, arguments);
        if (parameter === 37445) {
          const text = String(result || '');
          if (!text || /google/i.test(text)) {
            return config.webglVendor;
          }
        }
        if (parameter === 37446) {
          const text = String(result || '');
          if (!text || /swiftshader|google/i.test(text)) {
            return config.webglRenderer;
          }
        }
        return result;
      };
      markAsNative(wrapped, 'getParameter');
      wrapped.__codexStealthWrapped = true;
      safeDefineValue(Ctor.prototype, 'getParameter', wrapped);
    };
    patchWebGL(globalThis.WebGLRenderingContext);
    patchWebGL(globalThis.WebGL2RenderingContext);
  } catch (error) {}
})();
'''
    return script.replace("__CONFIG_JSON__", json.dumps(profile, ensure_ascii=False))
