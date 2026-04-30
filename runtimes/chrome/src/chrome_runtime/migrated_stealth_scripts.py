from __future__ import annotations

from typing import Final

WINDOW_OUTERDIMENSIONS_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (window.outerWidth && window.outerHeight) {
      return;
    }
    const windowFrame = 85;
    window.outerWidth = window.innerWidth;
    window.outerHeight = window.innerHeight + windowFrame;
  } catch (err) {}
})();
"""


IFRAME_CONTENT_WINDOW_SCRIPT: Final[str] = r"""
(() => {
  try {
    const currentCreateElement = document.createElement;
    if (typeof currentCreateElement !== 'function') {
      return;
    }
    if (currentCreateElement.__codexStealthIframeWrapped) {
      return;
    }

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
        get: () => proxy,
        set: (value) => value,
        enumerable: true,
        configurable: false,
      });
    };

    const originalCreateElement = currentCreateElement.bind(document);
    const wrappedCreateElement = function createElement(tagName) {
      const element = originalCreateElement.apply(this, arguments);
      if (String(tagName || '').toLowerCase() !== 'iframe') {
        return element;
      }

      const originalSrcdoc = element.srcdoc;
      Object.defineProperty(element, 'srcdoc', {
        configurable: true,
        get: () => originalSrcdoc,
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

    Object.defineProperty(wrappedCreateElement, '__codexStealthIframeWrapped', {
      value: true,
      configurable: false,
      enumerable: false,
      writable: false,
    });
    Object.defineProperty(document, 'createElement', {
      configurable: true,
      enumerable: true,
      writable: true,
      value: wrappedCreateElement,
    });
  } catch (err) {}
})();
"""


NAVIGATOR_VENDOR_SCRIPT: Final[str] = r"""
(() => {
  try {
    const proto = Object.getPrototypeOf(navigator);
    if (!proto) {
      return;
    }
    const current = Object.getOwnPropertyDescriptor(proto, 'vendor');
    if (current && typeof current.get === 'function') {
      try {
        const value = current.get.call(navigator);
        if (value === 'Google Inc.') {
          return;
        }
      } catch (err) {}
    }
    Object.defineProperty(proto, 'vendor', {
      get: () => 'Google Inc.',
      configurable: true,
    });
  } catch (err) {}
})();
"""


NAVIGATOR_HARDWARE_CONCURRENCY_SCRIPT: Final[str] = r"""
(() => {
  try {
    const proto = Object.getPrototypeOf(navigator);
    if (!proto) {
      return;
    }
    const current = Object.getOwnPropertyDescriptor(proto, 'hardwareConcurrency');
    if (current && typeof current.get === 'function') {
      try {
        const value = Number(current.get.call(navigator));
        if (value === 12) {
          return;
        }
      } catch (err) {}
    }
    Object.defineProperty(proto, 'hardwareConcurrency', {
      get: () => 12,
      configurable: true,
    });
  } catch (err) {}
})();
"""


NAVIGATOR_LANGUAGES_SCRIPT: Final[str] = r"""
(() => {
  try {
    const proto = Object.getPrototypeOf(navigator);
    if (!proto) {
      return;
    }
    const languages = Object.freeze(['en-US', 'en']);
    const current = Object.getOwnPropertyDescriptor(proto, 'languages');
    if (current && typeof current.get === 'function') {
      try {
        const value = current.get.call(navigator);
        const matches = Array.isArray(value)
          && value.length === languages.length
          && value.every((entry, index) => entry === languages[index]);
        if (matches) {
          return;
        }
      } catch (err) {}
    }
    Object.defineProperty(proto, 'languages', {
      get: () => languages,
      configurable: true,
    });
  } catch (err) {}
})();
"""


NAVIGATOR_PLUGINS_SCRIPT: Final[str] = r"""
(() => {
  try {
    if ('plugins' in navigator && navigator.plugins && navigator.plugins.length) {
      return;
    }

    const proto = Object.getPrototypeOf(navigator);
    if (!proto) {
      return;
    }

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
      const targetProto = ctor && ctor.prototype ? ctor.prototype : Object.prototype;
      const arr = Object.create(targetProto);
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
      const mimeProto = globalThis.MimeType && MimeType.prototype ? MimeType.prototype : Object.prototype;
      const mimeType = Object.create(mimeProto);
      safeDefineValue(mimeType, Symbol.toStringTag, 'MimeType', true, false, false);
      safeDefineValue(mimeType, 'type', String(data.type || ''), true, false, false);
      safeDefineValue(mimeType, 'suffixes', String(data.suffixes || ''), true, false, false);
      safeDefineValue(mimeType, 'description', String(data.description || ''), true, false, false);
      return mimeType;
    };

    const createPlugin = (data) => {
      const pluginProto = globalThis.Plugin && Plugin.prototype ? Plugin.prototype : Object.prototype;
      const plugin = Object.create(pluginProto);
      safeDefineValue(plugin, Symbol.toStringTag, 'Plugin', true, false, false);
      safeDefineValue(plugin, 'name', String(data.name || ''), true, false, false);
      safeDefineValue(plugin, 'filename', String(data.filename || ''), true, false, false);
      safeDefineValue(plugin, 'description', String(data.description || ''), true, false, false);
      return plugin;
    };

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
    safeDefineGetter(proto, 'mimeTypes', () => mimeTypeArray);
    safeDefineGetter(proto, 'plugins', () => pluginArray);
  } catch (err) {}
})();
"""


NAVIGATOR_PERMISSIONS_SCRIPT: Final[str] = r"""
(() => {
  try {
    const isSecure = String(document.location.protocol || '').startsWith('https');

    if (typeof Notification !== 'undefined' && isSecure) {
      try {
        Object.defineProperty(Notification, 'permission', {
          get: () => 'default',
          configurable: true,
        });
      } catch (err) {}
    }

    if (typeof Permissions !== 'undefined' && Permissions.prototype && !isSecure) {
      const originalQuery = Permissions.prototype.query;
      if (typeof originalQuery === 'function') {
        Permissions.prototype.query = function (...args) {
          const param = (args || [])[0];
          const isNotifications = param && param.name === 'notifications';
          if (!isNotifications) {
            return originalQuery.apply(this, args);
          }
          return Promise.resolve(Object.setPrototypeOf({
            state: 'denied',
            onchange: null,
          }, PermissionStatus.prototype));
        };
      }
    }
  } catch (err) {}
})();
"""


NAVIGATOR_WEBDRIVER_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (navigator.webdriver === false) {
      return;
    }
    if (navigator.webdriver === undefined) {
      return;
    }
    const proto = Object.getPrototypeOf(navigator);
    if (!proto) {
      return;
    }
    delete proto.webdriver;
  } catch (err) {}
})();
"""


CHROME_CSI_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        writable: true,
        enumerable: true,
        configurable: false,
        value: {},
      });
    }
    if ('csi' in window.chrome) {
      return;
    }
    if (!window.performance || !window.performance.timing) {
      return;
    }
    const { timing } = window.performance;
    window.chrome.csi = function () {
      return {
        onloadT: timing.domContentLoadedEventEnd,
        startE: timing.navigationStart,
        pageT: Date.now() - timing.navigationStart,
        tran: 15,
      };
    };
  } catch (err) {}
})();
"""


CHROME_APP_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        writable: true,
        enumerable: true,
        configurable: false,
        value: {},
      });
    }
    if ('app' in window.chrome) {
      return;
    }
    const staticData = {
      isInstalled: false,
      InstallState: {
        DISABLED: 'disabled',
        INSTALLED: 'installed',
        NOT_INSTALLED: 'not_installed',
      },
      RunningState: {
        CANNOT_RUN: 'cannot_run',
        READY_TO_RUN: 'ready_to_run',
        RUNNING: 'running',
      },
    };
    window.chrome.app = {
      ...staticData,
      get isInstalled() {
        return false;
      },
      getDetails: function getDetails() {
        if (arguments.length) {
          throw new TypeError('Error in invocation of app.getDetails()');
        }
        return null;
      },
      getIsInstalled: function getIsInstalled() {
        if (arguments.length) {
          throw new TypeError('Error in invocation of app.getIsInstalled()');
        }
        return false;
      },
      runningState: function runningState() {
        if (arguments.length) {
          throw new TypeError('Error in invocation of app.runningState()');
        }
        return 'cannot_run';
      },
    };
  } catch (err) {}
})();
"""


CHROME_LOADTIMES_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        writable: true,
        enumerable: true,
        configurable: false,
        value: {},
      });
    }
    if ('loadTimes' in window.chrome) {
      return;
    }
    if (!window.performance || !window.performance.timing || !window.PerformancePaintTiming) {
      return;
    }
    const { performance } = window;
    const ntEntryFallback = {
      nextHopProtocol: 'h2',
      type: 'other',
    };
    const protocolInfo = {
      get connectionInfo() {
        const ntEntry = performance.getEntriesByType('navigation')[0] || ntEntryFallback;
        return ntEntry.nextHopProtocol;
      },
      get npnNegotiatedProtocol() {
        const ntEntry = performance.getEntriesByType('navigation')[0] || ntEntryFallback;
        return ['h2', 'hq'].includes(ntEntry.nextHopProtocol) ? ntEntry.nextHopProtocol : 'unknown';
      },
      get navigationType() {
        const ntEntry = performance.getEntriesByType('navigation')[0] || ntEntryFallback;
        return ntEntry.type;
      },
      get wasAlternateProtocolAvailable() {
        return false;
      },
      get wasFetchedViaSpdy() {
        const ntEntry = performance.getEntriesByType('navigation')[0] || ntEntryFallback;
        return ['h2', 'hq'].includes(ntEntry.nextHopProtocol);
      },
      get wasNpnNegotiated() {
        const ntEntry = performance.getEntriesByType('navigation')[0] || ntEntryFallback;
        return ['h2', 'hq'].includes(ntEntry.nextHopProtocol);
      },
    };
    const { timing } = window.performance;
    function toFixed(num, fixed) {
      const re = new RegExp('^-?\d+(?:.\d{0,' + (fixed || -1) + '})?');
      return num.toString().match(re)[0];
    }
    const timingInfo = {
      get firstPaintAfterLoadTime() {
        return 0;
      },
      get requestTime() {
        return timing.navigationStart / 1000;
      },
      get startLoadTime() {
        return timing.navigationStart / 1000;
      },
      get commitLoadTime() {
        return timing.responseStart / 1000;
      },
      get finishDocumentLoadTime() {
        return timing.domContentLoadedEventEnd / 1000;
      },
      get finishLoadTime() {
        return timing.loadEventEnd / 1000;
      },
      get firstPaintTime() {
        const fpEntry = performance.getEntriesByType('paint')[0] || {
          startTime: timing.loadEventEnd / 1000,
        };
        return toFixed((fpEntry.startTime + performance.timeOrigin) / 1000, 3);
      },
    };
    window.chrome.loadTimes = function () {
      return {
        ...protocolInfo,
        ...timingInfo,
      };
    };
  } catch (err) {}
})();
"""


MEDIA_CODECS_SCRIPT: Final[str] = r"""
(() => {
  try {
    const parseInput = (arg) => {
      const [mime, codecStr] = String(arg || '').trim().split(';');
      let codecs = [];
      if (codecStr && codecStr.includes('codecs="')) {
        codecs = codecStr
          .trim()
          .replace('codecs="', '')
          .replace('"', '')
          .trim()
          .split(',')
          .filter(Boolean)
          .map((x) => x.trim());
      }
      return { mime, codecStr, codecs };
    };
    const original = HTMLMediaElement && HTMLMediaElement.prototype && HTMLMediaElement.prototype.canPlayType;
    if (typeof original !== 'function') {
      return;
    }
    HTMLMediaElement.prototype.canPlayType = function (...args) {
      if (!args || !args.length) {
        return original.apply(this, args);
      }
      const { mime, codecs } = parseInput(args[0]);
      if (mime === 'video/mp4' && codecs.includes('avc1.42E01E')) {
        return 'probably';
      }
      if (mime === 'audio/x-m4a' && !codecs.length) {
        return 'maybe';
      }
      if (mime === 'audio/aac' && !codecs.length) {
        return 'probably';
      }
      return original.apply(this, args);
    };
  } catch (err) {}
})();
"""


WEBGL_VENDOR_SCRIPT: Final[str] = r"""
(() => {
  try {
    const patch = (Proto) => {
      if (!Proto || typeof Proto.getParameter !== 'function') {
        return;
      }
      const original = Proto.getParameter;
      Proto.getParameter = function (...args) {
        const param = (args || [])[0];
        const result = original.apply(this, args);
        if (param === 37445) {
          return 'Intel Inc.';
        }
        if (param === 37446) {
          return 'Intel Iris OpenGL Engine';
        }
        return result;
      };
    };
    patch(globalThis.WebGLRenderingContext && WebGLRenderingContext.prototype);
    patch(globalThis.WebGL2RenderingContext && WebGL2RenderingContext.prototype);
  } catch (err) {}
})();
"""


CHROME_RUNTIME_SCRIPT: Final[str] = r"""
(() => {
  try {
    if (!window.chrome) {
      Object.defineProperty(window, 'chrome', {
        writable: true,
        enumerable: true,
        configurable: false,
        value: {},
      });
    }
    const existsAlready = 'runtime' in window.chrome;
    const isNotSecure = !String(window.location.protocol || '').startsWith('https');
    if (existsAlready || isNotSecure) {
      return;
    }
    const STATIC_DATA = {
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
    const makeCustomRuntimeErrors = (preamble, method, extensionId) => ({
      NoMatchingSignature: new TypeError(preamble + 'No matching signature.'),
      MustSpecifyExtensionID: new TypeError(
        preamble + `${method} called from a webpage must specify an Extension ID (string) for its first argument.`
      ),
      InvalidExtensionID: new TypeError(preamble + `Invalid extension id: '${extensionId}'`),
    });
    const isValidExtensionID = (str) =>
      typeof str === 'string' && str.length === 32 && !!str.toLowerCase().match(/^[a-p]+$/);

    const onSomething = () => ({
      addListener: function addListener() {},
      dispatch: function dispatch() {},
      hasListener: function hasListener() {},
      hasListeners: function hasListeners() { return false; },
      removeListener: function removeListener() {},
    });

    const makeConnectResponse = () => ({
      name: '',
      sender: undefined,
      disconnect: function disconnect() {},
      onDisconnect: onSomething(),
      onMessage: onSomething(),
      postMessage: function postMessage() {
        if (!arguments.length) {
          throw new TypeError('Insufficient number of arguments.');
        }
        throw new Error('Attempting to use a disconnected port object');
      },
    });

    window.chrome.runtime = {
      ...STATIC_DATA,
      get id() {
        return undefined;
      },
      sendMessage: function sendMessage(...args) {
        const [extensionId, options, responseCallback] = args || [];
        const errorPreamble = 'Error in invocation of runtime.sendMessage(optional string extensionId, any message, optional object options, optional function responseCallback): ';
        const Errors = makeCustomRuntimeErrors(errorPreamble, 'chrome.runtime.sendMessage()', extensionId);
        const noArguments = args.length === 0;
        const tooManyArguments = args.length > 4;
        const incorrectOptions = options && typeof options !== 'object';
        const incorrectResponseCallback = responseCallback && typeof responseCallback !== 'function';
        if (noArguments || tooManyArguments || incorrectOptions || incorrectResponseCallback) {
          throw Errors.NoMatchingSignature;
        }
        if (args.length < 2) {
          throw Errors.MustSpecifyExtensionID;
        }
        if (typeof extensionId !== 'string') {
          throw Errors.NoMatchingSignature;
        }
        if (!isValidExtensionID(extensionId)) {
          throw Errors.InvalidExtensionID;
        }
        return undefined;
      },
      connect: function connect(...args) {
        const [extensionId, connectInfo] = args || [];
        const errorPreamble = 'Error in invocation of runtime.connect(optional string extensionId, optional object connectInfo): ';
        const Errors = makeCustomRuntimeErrors(errorPreamble, 'chrome.runtime.connect()', extensionId);
        const noArguments = args.length === 0;
        const emptyStringArgument = args.length === 1 && extensionId === '';
        if (noArguments || emptyStringArgument) {
          throw Errors.MustSpecifyExtensionID;
        }
        const tooManyArguments = args.length > 2;
        const incorrectConnectInfoType = connectInfo && typeof connectInfo !== 'object';
        if (tooManyArguments || incorrectConnectInfoType) {
          throw Errors.NoMatchingSignature;
        }
        const extensionIdIsString = typeof extensionId === 'string';
        if (extensionIdIsString && extensionId === '') {
          throw Errors.MustSpecifyExtensionID;
        }
        if (extensionIdIsString && !isValidExtensionID(extensionId)) {
          throw Errors.InvalidExtensionID;
        }
        const validateConnectInfo = (ci) => {
          if (args.length > 1) {
            throw Errors.NoMatchingSignature;
          }
          if (Object.keys(ci).length === 0) {
            throw Errors.MustSpecifyExtensionID;
          }
          Object.entries(ci).forEach(([k, v]) => {
            const isExpected = ['name', 'includeTlsChannelId'].includes(k);
            if (!isExpected) {
              throw new TypeError(errorPreamble + `Unexpected property: '${k}'.`);
            }
            const mismatchError = (propName, expected, found) =>
              new TypeError(errorPreamble + `Error at property '${propName}': Invalid type: expected ${expected}, found ${found}.`);
            if (k === 'name' && typeof v !== 'string') {
              throw mismatchError(k, 'string', typeof v);
            }
            if (k === 'includeTlsChannelId' && typeof v !== 'boolean') {
              throw mismatchError(k, 'boolean', typeof v);
            }
          });
        };
        if (typeof extensionId === 'object' && extensionId !== null) {
          validateConnectInfo(extensionId);
          throw Errors.MustSpecifyExtensionID;
        }
        return makeConnectResponse();
      },
    };
  } catch (err) {}
})();
"""


def load_migrated_page_scripts() -> list[tuple[str, str]]:
    return [("window.outerdimensions", WINDOW_OUTERDIMENSIONS_SCRIPT), ("iframe.contentWindow", IFRAME_CONTENT_WINDOW_SCRIPT), ("navigator.vendor", NAVIGATOR_VENDOR_SCRIPT), ("navigator.hardwareConcurrency", NAVIGATOR_HARDWARE_CONCURRENCY_SCRIPT), ("navigator.languages", NAVIGATOR_LANGUAGES_SCRIPT), ("navigator.plugins", NAVIGATOR_PLUGINS_SCRIPT), ("navigator.permissions", NAVIGATOR_PERMISSIONS_SCRIPT), ("navigator.webdriver", NAVIGATOR_WEBDRIVER_SCRIPT), ("chrome.csi", CHROME_CSI_SCRIPT), ("chrome.app", CHROME_APP_SCRIPT), ("chrome.loadTimes", CHROME_LOADTIMES_SCRIPT), ("media.codecs", MEDIA_CODECS_SCRIPT), ("webgl.vendor", WEBGL_VENDOR_SCRIPT), ("chrome.runtime", CHROME_RUNTIME_SCRIPT)]
