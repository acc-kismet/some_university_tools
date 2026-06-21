// ==UserScript==
// @name         回放 is all you need
// @namespace    http://tampermonkey.net/
// @version      2.1
// @description  从课程列表页提取信息，通过请求目标视频页获取HLS URL，支持批量选择视频流，按顺序下载选中视频流 (内部并发10)。同时强制开启 jxypt.hitsz.edu.cn 上的视频回放权限，并添加左右箭头快进快退 10 秒的功能。
// @author       You & Acc (Combined)
// @match        https://jxypt.hitsz.edu.cn/*
// @grant        GM.xmlHttpRequest
// @run-at       document-idle
// ==/UserScript==

(function() {
    'use strict';

    // ====================================================================
    // !!! 核心配置和常量 !!!
    // ====================================================================
    const VIDEO_PAGE_URL_TEMPLATE = `https://jxypt.hitsz.edu.cn:443/ve/back/rp/common/rpIndex.shtml?method=studyCourseDeatil&courseId={id2}&courseNum={courseCode}&rpId={id1}&dataSource=1`;
    const CURRENT_VERSION = '2.1';
    const PANEL_WIDTH = '1520px';
    const PANEL_HEIGHT = '680px';
    const SKIP_AMOUNT = 10;
    const VIDEO_SELECTOR = 'video';
    const MAX_ATTEMPTS = 50;
    const REFRESH_DELAY = 150;
    const PANEL_ID = 'video-downloader-panel-batch';
    const STYLE_ID = 'course-helper-dashboard-style';
    const REPLAY_SELECTOR = '[onclick*="getStuControlType("]';
    const COURSE_LIST_SELECTOR = 'ul.curr-contentr-title.curr-contentr-list.clearfloat';
    const MAIN_COURSE_SELECTOR = 'span.topm';

    const GOOGLE_LOGO_COLORS = {
        blue: '#4285F4',
        red: '#EA4335',
        yellow: '#FBBC05',
        green: '#34A853',
    };

    const NEUTRAL_COLORS = {
        white: '#ffffff',
        bg: '#f5f7fa',
        surfaceSoft: '#f3f4f6',
        border: '#e5e7eb',
        borderStrong: '#d1d5db',
        text: '#374151',
        muted: '#6b7280',
    };

    const THEME_COLORS = {
        accent: GOOGLE_LOGO_COLORS.blue,
        accentDark: GOOGLE_LOGO_COLORS.blue,
        accentDeep: GOOGLE_LOGO_COLORS.green,
        info: GOOGLE_LOGO_COLORS.blue,
        success: GOOGLE_LOGO_COLORS.green,
        error: GOOGLE_LOGO_COLORS.red,
        warn: GOOGLE_LOGO_COLORS.yellow,
        badgeText: NEUTRAL_COLORS.white,
    };

    const STREAM_TYPES = [
        { key: 'teaUrl', name: '教师流', icon: 'userTie' },
        { key: 'stuUrl', name: '学生流', icon: 'video' },
        { key: 'vgaUrl', name: '课件流', icon: 'fileLines' }
    ];

    const QUICK_SELECT_ACTIONS = [
        { key: 'teacher', selectLabel: '全选教师流', cancelLabel: '取消教师流', streamKeys: ['teaUrl'], icon: 'userTie' },
        { key: 'teacherCourseware', selectLabel: '全选教师流 + 课件流', cancelLabel: '取消教师流 + 课件流', streamKeys: ['teaUrl', 'vgaUrl'], icon: 'layerGroup' },
        { key: 'courseware', selectLabel: '全选课件流', cancelLabel: '取消课件流', streamKeys: ['vgaUrl'], icon: 'fileLines' }
    ];

    const MODERN_ICONS = {
        bolt: '<svg viewBox="0 0 24 24"><path d="M13 2 4 14h7l-1 8 9-12h-7l1-8Z"/></svg>',
        chevronUp: '<svg viewBox="0 0 24 24"><path d="m6 15 6-6 6 6"/></svg>',
        download: '<svg viewBox="0 0 24 24"><path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 21h14"/></svg>',
        fileLines: '<svg viewBox="0 0 24 24"><path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7l-5-5Z"/><path d="M14 2v5h5"/><path d="M8 13h8"/><path d="M8 17h6"/></svg>',
        layerGroup: '<svg viewBox="0 0 24 24"><path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5"/><path d="m3 16 9 5 9-5"/></svg>',
        gripVertical: '<svg viewBox="0 0 24 24"><path d="M9 6h.01"/><path d="M15 6h.01"/><path d="M9 12h.01"/><path d="M15 12h.01"/><path d="M9 18h.01"/><path d="M15 18h.01"/></svg>',
        userTie: '<svg viewBox="0 0 24 24"><circle cx="12" cy="7" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/><path d="m10 14 2 2 2-2"/><path d="m11 16-1 5"/><path d="m13 16 1 5"/></svg>',
        video: '<svg viewBox="0 0 24 24"><rect x="3" y="6" width="13" height="12" rx="3"/><path d="m16 10 5-3v10l-5-3v-4Z"/></svg>'
    };

    const uiState = {
        isExpanded: false,
        selectedStreamKeys: new Set(),
        observerInitialized: false,
        refreshTimer: null,
        lastVideoSignature: '',
        replayInterceptorInitialized: false,
        videos: [],
        selectionScrollTop: 0,
        statusScrollTop: 0,
        downloadTasks: [],
        isDownloading: false,
    };

    let attempts = 0;

    /** 从 onclick 字符串解析回放参数 rpId/courseId/courseNum/fzId */
    function parseReplayParams(onclickString) {
        const match = onclickString && onclickString.match(/getStuControlType\('(.*?)','(.*?)','(.*?)','(.*?)'\)/);
        if (!match || match.length !== 5) { // 格式不匹配
            return null;
        }

        return {
            rpId: match[1],
            courseId: match[2],
            courseNum: match[3],
            fzId: match[4],
        };
    }

    /** 构造回放页面相对 URL */
    function buildReplayUrl(rpId, courseId, courseNum, fzId) {
        const publicRpType = '2,3';
        return `../../../back/rp/common/rpIndex.shtml?method=studyCourseDeatil&courseId=${courseId}&dataSource=1&courseNum=${courseNum}&fzId=${fzId}&rpId=${rpId}&publicRpType=${publicRpType}`;
    }

    /** 生成流勾选的唯一键 */
    function buildStreamSelectionKey(videoInfo, streamKey) {
        return `${videoInfo.id1}::${streamKey}`;
    }

    /** 生成课程列表签名，用于检测 DOM 是否变化 */
    function buildVideoSignature(videos) {
        return videos.map(video => `${video.id1}|${video.id2}|${video.courseCode}|${video.courseName}`).join('||');
    }

    /** 解析 m3u8 播放列表，提取分片 URL */
    function parseSegments(playlistContent, baseUrl) {
        const segments = [];
        const lines = playlistContent.split('\n');
        const base = baseUrl.substring(0, baseUrl.lastIndexOf('/') + 1);

        for (const line of lines) {
            if (line && !line.startsWith('#') && (line.endsWith('.ts') || line.endsWith('.mp4'))) { // 有效分片行
                const fullUrl = line.startsWith('http') ? line : base + line; // 补全相对路径
                segments.push(fullUrl.trim());
            }
        }
        return segments;
    }

    /** 通过 GM.xmlHttpRequest 跨域请求资源 */
    function tampermonkeyFetch(url, responseType = 'text') {
        return new Promise((resolve, reject) => {
            if (typeof GM === 'undefined' || typeof GM.xmlHttpRequest === 'undefined') { // 无 GM 权限
                reject(new Error("GM.xmlHttpRequest is not available. Please ensure '@grant GM.xmlHttpRequest' is in the script header."));
                return;
            }

            GM.xmlHttpRequest({
                method: 'GET',
                url: url,
                responseType: responseType,
                onload: function(response) {
                    if (response.status >= 200 && response.status < 300) { // HTTP 成功
                        resolve(response.response);
                    } else {
                        console.error(`[GM_XHR Error] Status: ${response.status} ${response.statusText}`, response);
                        reject(new Error(`Fetch error: ${response.status} ${response.statusText} for ${url}`));
                    }
                },
                onerror: function(error) {
                    reject(error);
                }
            });
        });
    }

    /** 从回放页 HTML 提取三路 HLS 地址 */
    function extractHlsUrlsFromHtml(htmlContent) {
        const regexTea = /var\s+teaStreamHlsUrl\s*=\s*"(.*?)"/s;
        const regexStu = /var\s+stuStreamHlsUrl\s*=\s*"(.*?)"/s;
        const regexVga = /var\s+vgaStreamHlsUrl\s*=\s*"(.*?)"/s;

        return {
            teaUrl: (htmlContent.match(regexTea) || [])[1],
            stuUrl: (htmlContent.match(regexStu) || [])[1],
            vgaUrl: (htmlContent.match(regexVga) || [])[1]
        };
    }

    /** 注入下载面板 CSS，仅执行一次 */
    function ensurePanelStyles() {
        if (document.getElementById(STYLE_ID)) { // 样式已存在
            return;
        }

        const style = document.createElement('style');
        style.id = STYLE_ID;
        style.textContent = `
            #${PANEL_ID} {
                --google-blue: ${GOOGLE_LOGO_COLORS.blue};
                --google-red: ${GOOGLE_LOGO_COLORS.red};
                --google-yellow: ${GOOGLE_LOGO_COLORS.yellow};
                --google-green: ${GOOGLE_LOGO_COLORS.green};
                --ch-bg: ${NEUTRAL_COLORS.bg};
                --ch-surface: ${NEUTRAL_COLORS.white};
                --ch-surface-soft: ${NEUTRAL_COLORS.surfaceSoft};
                --ch-border: ${NEUTRAL_COLORS.border};
                --ch-border-strong: ${NEUTRAL_COLORS.borderStrong};
                --ch-shadow: 0 18px 42px rgba(107, 114, 128, 0.14);
                --ch-text: ${NEUTRAL_COLORS.text};
                --ch-muted: ${NEUTRAL_COLORS.muted};
                --ch-accent: var(--google-blue);
                --ch-accent-dark: var(--google-blue);
                --ch-accent-deep: var(--google-green);
                --ch-accent-soft: ${NEUTRAL_COLORS.surfaceSoft};
                position: fixed;
                top: 18px;
                right: 18px;
                width: 348px;
                height: 68px;
                overflow: hidden;
                border-radius: 18px;
                border: 1px solid var(--ch-border);
                box-shadow: var(--ch-shadow);
                background: var(--ch-surface);
                color: var(--ch-text);
                z-index: 10000;
                font-family: "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
                transition: width 0.24s ease, height 0.24s ease, transform 0.2s ease;
            }

            #${PANEL_ID}.is-expanded {
                width: min(${PANEL_WIDTH}, calc(100vw - 36px));
                height: min(${PANEL_HEIGHT}, calc(100vh - 36px));
                background: var(--ch-bg);
                overflow: hidden;
            }

            #${PANEL_ID} * {
                box-sizing: border-box;
            }

            #${PANEL_ID} button,
            #${PANEL_ID} input {
                font: inherit;
            }

            .course-helper__icon {
                width: 16px;
                height: 16px;
                display: inline-block;
                flex: 0 0 auto;
                fill: none;
                stroke: currentColor;
                stroke-width: 2;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .course-helper__icon--lg {
                width: 22px;
                height: 22px;
            }

            .course-helper__folded {
                display: flex;
                align-items: center;
                gap: 10px;
                height: 100%;
                padding: 12px 14px;
                cursor: pointer;
                color: var(--ch-accent-deep);
            }

            .course-helper__folded-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 38px;
                height: 38px;
                border-radius: 12px;
                background: ${NEUTRAL_COLORS.white};
                color: var(--ch-accent);
                box-shadow: 0 8px 18px rgba(107, 114, 128, 0.12);
            }

            .course-helper__folded-copy {
                display: flex;
                flex-direction: column;
                min-width: 0;
                flex: 1;
            }

            .course-helper__folded-title {
                font-size: 13px;
                font-weight: 800;
                white-space: nowrap;
            }

            .course-helper__folded-meta {
                margin-top: 2px;
                font-size: 11px;
                color: var(--ch-muted);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .course-helper__expanded {
                display: none;
                height: 100%;
                padding: 14px;
                background: var(--ch-bg);
            }

            #${PANEL_ID}.is-expanded .course-helper__expanded {
                display: block;
            }

            #${PANEL_ID}.is-expanded .course-helper__folded {
                display: none;
            }

            .course-helper__shell {
                display: grid;
                grid-template-rows: auto minmax(0, 1fr);
                gap: 12px;
                height: 100%;
            }

            .course-helper__hero,
            .course-helper__section,
            .course-helper__status-shell {
                border-radius: 16px;
                border: 1px solid var(--ch-border);
                background: var(--ch-surface);
                box-shadow: 0 10px 24px rgba(107, 114, 128, 0.08);
            }

            .course-helper__hero {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 14px;
                padding: 14px 16px;
            }

            .course-helper__brand {
                display: flex;
                align-items: center;
                min-width: 0;
                gap: 12px;
            }

            .course-helper__brand-mark {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border-radius: 16px;
                background: ${NEUTRAL_COLORS.white};
                color: var(--ch-accent);
                box-shadow: 0 10px 22px rgba(107, 114, 128, 0.1);
            }

            .course-helper__eyebrow {
                display: block;
                color: var(--ch-accent-dark);
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.06em;
            }

            .course-helper__title {
                margin: 2px 0 3px;
                font-size: 19px;
                font-weight: 900;
                line-height: 1.2;
                color: var(--ch-text);
            }

            .course-helper__subtitle {
                margin: 0;
                color: var(--ch-muted);
                font-size: 12px;
                line-height: 1.35;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .course-helper__collapse {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border: 1px solid var(--ch-border);
                background: var(--ch-surface-soft);
                color: var(--ch-accent-dark);
                width: 40px;
                height: 40px;
                border-radius: 12px;
                cursor: pointer;
                transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease;
            }

            .course-helper__collapse:hover,
            .course-helper__quick-select:hover {
                border-color: var(--ch-border-strong);
                color: var(--ch-accent);
                transform: translateY(-1px);
            }

            .course-helper__main {
                display: grid;
                grid-template-columns: minmax(0, 1fr) 520px;
                gap: 12px;
                min-height: 0;
            }

            .course-helper__section,
            .course-helper__status-shell {
                min-height: 0;
                padding: 14px;
            }

            .course-helper__section {
                display: grid;
                grid-template-rows: auto auto minmax(0, 1fr) auto;
                gap: 12px;
            }

            .course-helper__status-shell {
                display: grid;
                grid-template-rows: auto auto auto minmax(0, 1fr);
                gap: 12px;
            }

            .course-helper__section-head {
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
            }

            .course-helper__section-title {
                margin: 0;
                font-size: 15px;
                font-weight: 900;
                color: var(--ch-text);
            }

            .course-helper__section-hint {
                margin: 4px 0 0;
                font-size: 12px;
                color: var(--ch-muted);
                line-height: 1.4;
            }

            .course-helper__quick-actions {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 8px;
            }

            .course-helper__quick-select {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 6px;
                min-height: 38px;
                border: 1px solid var(--ch-border);
                border-radius: 12px;
                background: var(--ch-surface-soft);
                color: var(--ch-accent-deep);
                cursor: pointer;
                font-size: 12px;
                font-weight: 800;
                transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
            }

            .course-helper__quick-select:disabled {
                cursor: not-allowed;
                opacity: 0.55;
                transform: none;
            }

            .course-helper__quick-select.is-active {
                background: var(--google-yellow);
                border-color: var(--google-yellow);
                color: var(--ch-text);
            }

            .course-helper__selection {
                height: 338px;
                overflow: auto;
                display: grid;
                align-content: start;
                gap: 10px;
                padding-right: 4px;
            }

            .course-helper__course {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 10px;
                padding: 12px;
                border-radius: 14px;
                border: 1px solid var(--ch-border);
                background: var(--ch-surface);
            }

            .course-helper__course-title {
                font-size: 13px;
                font-weight: 800;
                color: var(--ch-text);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .course-helper__course-meta {
                margin-top: 4px;
                color: var(--ch-muted);
                font-size: 11px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .course-helper__stream-group {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }

            .course-helper__stream {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                padding: 7px 9px;
                border-radius: 999px;
                border: 1px solid var(--ch-border);
                background: var(--ch-surface-soft);
                color: var(--ch-accent-deep);
                cursor: pointer;
                transition: border-color 0.2s ease, color 0.2s ease;
                font-size: 12px;
                font-weight: 700;
            }

            .course-helper__stream:hover {
                border-color: var(--ch-border-strong);
                color: var(--ch-accent);
            }

            .course-helper__stream input {
                margin: 0;
                accent-color: var(--ch-accent);
            }

            .course-helper__empty {
                padding: 24px 16px;
                border-radius: 14px;
                text-align: center;
                color: var(--ch-muted);
                background: var(--ch-surface-soft);
                border: 1px dashed var(--ch-border-strong);
                font-size: 13px;
                line-height: 1.5;
            }

            .course-helper__submit {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                width: 100%;
                border: 1px solid var(--ch-accent);
                border-radius: 14px;
                padding: 12px 16px;
                background: var(--ch-accent);
                color: ${NEUTRAL_COLORS.white};
                cursor: pointer;
                font-size: 14px;
                font-weight: 900;
                letter-spacing: 0.01em;
                box-shadow: 0 12px 20px rgba(66, 133, 244, 0.24);
                transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
            }

            .course-helper__submit:disabled {
                cursor: not-allowed;
                opacity: 0.6;
                box-shadow: none;
                transform: none;
            }

            .course-helper__submit .course-helper__icon {
                stroke: ${NEUTRAL_COLORS.white};
            }

            .course-helper__submit:hover:not(:disabled) {
                background: var(--google-green);
                border-color: var(--google-green);
                color: ${NEUTRAL_COLORS.white};
                transform: translateY(-1px);
            }

            .course-helper__queue-start {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                width: 100%;
                min-height: 38px;
                border: 1px solid var(--ch-border-strong);
                border-radius: 12px;
                background: var(--ch-accent-soft);
                color: var(--ch-accent-deep);
                cursor: pointer;
                font-size: 12px;
                font-weight: 900;
                transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, opacity 0.2s ease;
            }

            .course-helper__queue-start:hover:not(:disabled) {
                border-color: var(--ch-accent);
                background: ${NEUTRAL_COLORS.white};
                color: var(--ch-accent);
                transform: translateY(-1px);
            }

            .course-helper__queue-start:disabled {
                cursor: not-allowed;
                opacity: 0.58;
                transform: none;
            }

            .course-helper__queue-start[hidden] {
                display: none;
            }

            .course-helper__metrics {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 8px;
            }

            .course-helper__metric {
                padding: 10px;
                border-radius: 12px;
                background: var(--ch-surface-soft);
                border: 1px solid var(--ch-border);
            }

            .course-helper__metric-label {
                display: block;
                font-size: 11px;
                color: var(--ch-muted);
                margin-bottom: 5px;
            }

            .course-helper__metric-value {
                display: block;
                color: var(--ch-accent-deep);
                font-size: 17px;
                font-weight: 900;
            }

            .course-helper__status-list {
                list-style: none;
                margin: 0;
                padding: 0;
                height: 328px;
                overflow: auto;
                display: grid;
                align-content: start;
                gap: 9px;
            }

            .course-helper__status-item {
                display: grid;
                grid-template-columns: minmax(0, 1fr);
                gap: 8px;
                padding: 11px;
                border-radius: 13px;
                background: var(--ch-surface);
                border: 1px solid var(--ch-border);
            }

            .course-helper__queue-item {
                grid-template-columns: auto minmax(0, 1fr);
                cursor: grab;
            }

            .course-helper__queue-item:active {
                cursor: grabbing;
            }

            .course-helper__queue-item.is-dragging {
                opacity: 0.48;
                border-color: var(--ch-accent);
            }

            .course-helper__queue-item[data-state="running"],
            .course-helper__queue-item[data-state="done"],
            .course-helper__queue-item[data-state="failed"] {
                cursor: default;
            }

            .course-helper__queue-item[data-state="done"],
            .course-helper__queue-item[data-state="failed"] {
                opacity: 0.78;
                background: var(--ch-surface-soft);
            }

            .course-helper__drag-handle {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 18px;
                min-height: 32px;
                color: var(--ch-muted);
                grid-row: span 2;
            }

            .course-helper__queue-item[data-state="running"] .course-helper__drag-handle,
            .course-helper__queue-item[data-state="done"] .course-helper__drag-handle,
            .course-helper__queue-item[data-state="failed"] .course-helper__drag-handle {
                opacity: 0.35;
            }

            .course-helper__status-name {
                min-width: 0;
                font-size: 12px;
                font-weight: 800;
                color: var(--ch-text);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }

            .course-helper__status-badge {
                width: fit-content;
                max-width: 100%;
                padding: 6px 9px;
                border-radius: 999px;
                color: ${NEUTRAL_COLORS.white};
                text-align: center;
                font-size: 11px;
                font-weight: 800;
            }

            .course-helper__queue-item .course-helper__status-badge {
                grid-column: 2;
            }

            .course-helper__status-placeholder {
                padding: 14px;
                text-align: center;
                color: var(--ch-muted);
                border-radius: 13px;
                background: var(--ch-surface-soft);
                border: 1px dashed var(--ch-border-strong);
                font-size: 13px;
                line-height: 1.5;
            }

            .course-helper__status-final {
                padding: 12px 14px;
                border-radius: 13px;
                text-align: center;
                font-weight: 900;
                color: var(--google-green);
                background: ${NEUTRAL_COLORS.white};
                border: 1px solid var(--google-green);
            }

            @media (max-width: 1560px) {
                #${PANEL_ID}.is-expanded {
                    width: calc(100vw - 18px);
                    height: calc(100vh - 18px);
                    right: 9px;
                    top: 9px;
                }

                .course-helper__main {
                    grid-template-columns: 1fr;
                    overflow: auto;
                    padding-right: 2px;
                }

                .course-helper__selection,
                .course-helper__status-list {
                    height: 260px;
                }
            }

            @media (max-height: 760px) {
                .course-helper__selection {
                    height: 260px;
                }

                .course-helper__status-list {
                    height: 240px;
                }
            }
        `;
        document.head.appendChild(style);
    }

    /** 转义 HTML 特殊字符，防 XSS */
    function escapeHtml(value) {
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /** 输出内联现代线性 SVG 图标 */
    function iconSvg(name, extraClass = '') {
        const svg = MODERN_ICONS[name];
        if (!svg) {
            return '';
        }

        const classes = `course-helper__icon${extraClass ? ` ${extraClass}` : ''}`;
        return svg.replace('<svg ', `<svg class="${classes}" aria-hidden="true" focusable="false" `);
    }

    /** 创建单条下载状态 DOM 节点 */
    function createStatusItem(stream, initialMessage) {
        const statusItem = document.createElement('li');
        statusItem.id = `status-${stream.videoInfo.id1}-${stream.streamKey}`;
        statusItem.className = 'course-helper__status-item';

        const nameSpan = document.createElement('span');
        nameSpan.className = 'course-helper__status-name';
        nameSpan.title = `${stream.videoInfo.courseName} - ${stream.streamName}`;
        nameSpan.textContent = `${stream.videoInfo.courseName} - ${stream.streamName}`;

        const statusElement = document.createElement('div');
        statusElement.className = 'course-helper__status-badge';
        statusElement.textContent = initialMessage;
        statusElement.style.backgroundColor = THEME_COLORS.info;

        statusItem.appendChild(nameSpan);
        statusItem.appendChild(statusElement);
        return { item: statusItem, element: statusElement };
    }

    /** 更新状态徽章文字与颜色 */
    function updateStatus(element, message, type = 'info') {
        element.textContent = message;
        element.style.color = THEME_COLORS.badgeText;
        element.style.backgroundColor = THEME_COLORS[type] || THEME_COLORS.info;
        element.style.display = 'block';
    }

    /** 生成下载任务唯一键 */
    function buildDownloadTaskId(stream) {
        return buildStreamSelectionKey(stream.videoInfo, stream.streamKey);
    }

    /** 标记队列任务状态，并控制是否可拖拽 */
    function setQueueTaskState(task, state) {
        task.state = state;
        if (!task.item) {
            return;
        }

        const isPending = state === 'pending';
        task.item.dataset.state = state;
        task.item.draggable = isPending;
        task.item.setAttribute('aria-grabbed', 'false');
    }

    /** 创建队列任务 DOM 节点 */
    function createDownloadQueueItem(task, orderIndex) {
        const status = createStatusItem(task.stream, `等待排序 #${orderIndex + 1}`);
        const dragHandle = document.createElement('span');
        dragHandle.className = 'course-helper__drag-handle';
        dragHandle.innerHTML = iconSvg('gripVertical');
        dragHandle.title = '拖拽调整下载顺序';

        status.item.classList.add('course-helper__queue-item');
        status.item.dataset.taskId = task.id;
        status.item.insertBefore(dragHandle, status.item.firstChild);

        task.item = status.item;
        task.statusElement = status.element;
        setQueueTaskState(task, 'pending');
        return status.item;
    }

    /** 根据 DOM 顺序同步队列数组 */
    function syncDownloadTaskOrderFromDom(statusList) {
        const taskMap = new Map(uiState.downloadTasks.map(task => [task.id, task]));
        uiState.downloadTasks = Array.from(statusList.querySelectorAll('.course-helper__queue-item'))
            .map(item => taskMap.get(item.dataset.taskId))
            .filter(Boolean);
    }

    /** 按当前 DOM 顺序更新未下载任务的等待序号 */
    function updatePendingQueueOrderLabels(statusList) {
        syncDownloadTaskOrderFromDom(statusList);
        let pendingIndex = 1;
        uiState.downloadTasks.forEach(task => {
            if (task.state !== 'pending' || !task.statusElement) {
                return;
            }

            task.statusElement.textContent = `等待排序 #${pendingIndex}`;
            pendingIndex++;
        });
    }

    /** 找到拖拽插入位置，只在未下载任务中排序 */
    function getPendingDragAfterElement(statusList, y) {
        const pendingItems = Array.from(statusList.querySelectorAll('.course-helper__queue-item[data-state="pending"]:not(.is-dragging)'));
        return pendingItems.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            }
            return closest;
        }, { offset: Number.NEGATIVE_INFINITY, element: null }).element;
    }

    /** 绑定队列拖拽排序事件 */
    function bindDownloadQueueDrag(statusList) {
        if (!statusList || statusList.dataset.dragBound === 'true') {
            return;
        }

        statusList.addEventListener('dragstart', function(event) {
            if (!(event.target instanceof Element)) {
                event.preventDefault();
                return;
            }

            const item = event.target.closest('.course-helper__queue-item');
            if (!item || item.dataset.state !== 'pending') {
                event.preventDefault();
                return;
            }

            item.classList.add('is-dragging');
            item.setAttribute('aria-grabbed', 'true');
            if (event.dataTransfer) {
                event.dataTransfer.effectAllowed = 'move';
                event.dataTransfer.setData('text/plain', item.dataset.taskId || '');
            }
        });

        statusList.addEventListener('dragover', function(event) {
            const draggingItem = statusList.querySelector('.course-helper__queue-item.is-dragging');
            if (!draggingItem) {
                return;
            }

            event.preventDefault();
            const afterElement = getPendingDragAfterElement(statusList, event.clientY);
            if (afterElement) {
                statusList.insertBefore(draggingItem, afterElement);
            } else {
                const firstCompleted = statusList.querySelector('.course-helper__queue-item[data-state="done"], .course-helper__queue-item[data-state="failed"]');
                statusList.insertBefore(draggingItem, firstCompleted);
            }
            updatePendingQueueOrderLabels(statusList);
        });

        statusList.addEventListener('dragend', function(event) {
            if (!(event.target instanceof Element)) {
                updatePendingQueueOrderLabels(statusList);
                return;
            }

            const item = event.target.closest('.course-helper__queue-item');
            if (item) {
                item.classList.remove('is-dragging');
                item.setAttribute('aria-grabbed', 'false');
            }
            updatePendingQueueOrderLabels(statusList);
        });

        statusList.dataset.dragBound = 'true';
    }

    /** 渲染待下载队列，等待用户拖拽排序后启动 */
    function renderDownloadQueue(selectedStreams) {
        const downloadStatusList = document.getElementById('download-status-list');
        const startBtn = document.getElementById('start-download-btn');
        if (!downloadStatusList || !startBtn) {
            return;
        }

        uiState.downloadTasks = selectedStreams.map(stream => ({
            id: buildDownloadTaskId(stream),
            stream: stream,
            state: 'pending',
            item: null,
            statusElement: null,
        }));

        downloadStatusList.innerHTML = '';
        uiState.downloadTasks.forEach((task, index) => {
            downloadStatusList.appendChild(createDownloadQueueItem(task, index));
        });
        bindDownloadQueueDrag(downloadStatusList);
        updatePendingQueueOrderLabels(downloadStatusList);

        startBtn.hidden = false;
        startBtn.disabled = false;
        const startLabel = startBtn.querySelector('span');
        if (startLabel) {
            startLabel.textContent = '按当前顺序开始下载';
        }
    }

    /** 并发下载分片并合并为 ts 文件触发浏览器下载 */
    async function downloadAndMergeSegments(segments, streamName, statusElement) {
        if (segments.length === 0) { // 无分片
            updateStatus(statusElement, '错误：未找到视频分片。', 'error');
            return false;
        }

        const totalSegments = segments.length;
        updateStatus(statusElement, `开始下载 ${totalSegments} 个分片... (并发限制: 10)`, 'info');

        let completedCount = 0;
        let failedCount = 0;
        const allResults = [];
        const concurrencyLimit = 10;

        for (let i = 0; i < totalSegments; i += concurrencyLimit) {
            const chunk = segments.slice(i, i + concurrencyLimit);

            const downloadPromises = chunk.map((segmentUrl, indexInChunk) => {
                const originalIndex = i + indexInChunk;
                return tampermonkeyFetch(segmentUrl, 'arraybuffer')
                    .then(buffer => {
                        completedCount++;
                        updateStatus(statusElement, `(${completedCount}/${totalSegments})，失败 ${failedCount} 个`, 'info');
                        return { status: 'fulfilled', buffer: buffer, index: originalIndex };
                    })
                    .catch(error => {
                        completedCount++;
                        failedCount++;
                        updateStatus(statusElement, `(${completedCount}/${totalSegments})，失败 ${failedCount} 个`, failedCount > 0 ? 'error' : 'info');
                        console.error(`分片下载失败 (Index: ${originalIndex}, URL: ${segmentUrl}):`, error);
                        return { status: 'rejected', reason: error, index: originalIndex };
                    });
            });

            const chunkResults = await Promise.all(downloadPromises);
            allResults.push(...chunkResults);
        }

        const buffers = [];
        let successCount = 0;
        allResults.sort((a, b) => a.index - b.index);

        for (const result of allResults) {
            if (result.status === 'fulfilled') { // 分片成功
                buffers.push(new Uint8Array(result.buffer));
                successCount++;
            }
        }

        if (successCount === 0) { // 全部失败
            updateStatus(statusElement, '错误：所有分片下载均失败。', 'error');
            return false;
        }

        updateStatus(statusElement, '下载完成，开始合并分片...', 'success');
        const mergedBlob = new Blob(buffers, { type: 'video/mp2t' });

        const date = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const filename = `${streamName}_${date}.ts`;
        const url = URL.createObjectURL(mergedBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        updateStatus(statusElement, `✅ 成功合并并下载 (失败 ${failedCount} 个分片).`, 'success');
        return true;
    }

    /** 单路视频流完整下载流程：页面→HLS→分片→合并 */
    async function handleStreamDownload({ videoInfo, streamKey, streamName }, statusElement) {
        const fullStreamName = `${videoInfo.courseName}_${streamName}`;
        let videoPageUrl;

        try {
            videoPageUrl = VIDEO_PAGE_URL_TEMPLATE
                .replace('{id1}', videoInfo.id1)
                .replace('{id2}', videoInfo.id2)
                .replace('{courseCode}', videoInfo.courseCode);

            updateStatus(statusElement, '正在请求 HLS URL...', 'info');

            const htmlContent = await tampermonkeyFetch(videoPageUrl, 'text');
            const hlsUrls = extractHlsUrlsFromHtml(htmlContent);
            const hlsUrl = hlsUrls[streamKey];

            if (!hlsUrl) { // 该流不存在
                throw new Error(`未找到 ${streamName} 的 HLS URL。`);
            }

            updateStatus(statusElement, '正在请求播放列表...', 'info');
            const playlistContent = await tampermonkeyFetch(hlsUrl, 'text');
            const segmentUrls = parseSegments(playlistContent, hlsUrl);

            const success = await downloadAndMergeSegments(segmentUrls, fullStreamName, statusElement);
            return success;
        } catch (error) {
            console.error(`[${fullStreamName}] 下载失败:`, error);
            const errorMessage = `下载失败: ${error.message.substring(0, 60)}...`;
            updateStatus(statusElement, errorMessage, 'error');
            return false;
        }
    }

    /** 从当前页面 DOM 提取课程回放列表 */
    function extractVideoInfo() {
        const ulList = document.querySelectorAll(COURSE_LIST_SELECTOR);
        const videos = [];

        const mainCourseSpan = document.querySelector(MAIN_COURSE_SELECTOR);
        const mainCourseTitle = mainCourseSpan ? mainCourseSpan.textContent.trim() : '未知课程';

        ulList.forEach(ulElement => {
            const aTag = ulElement.querySelector('a');
            if (!aTag || !aTag.getAttribute('onclick')) { // 无回放入口
                return;
            }

            const listItems = ulElement.querySelectorAll('li');
            let dateName = '';
            let teacherName = '';

            if (listItems.length > 0) {
                dateName = listItems[0].textContent.trim();
                if (listItems.length >= 4) {
                    teacherName = listItems[3].textContent.trim();
                }
                const courseName = `${mainCourseTitle}_${dateName}_${teacherName}`;
                const replayParams = parseReplayParams(aTag.getAttribute('onclick'));

                if (replayParams) { // 参数解析成功
                    videos.push({
                        courseName: courseName,
                        id1: replayParams.rpId,
                        id2: replayParams.courseId,
                        courseCode: replayParams.courseNum,
                        fullCode: replayParams.fzId,
                    });
                }
            }
        });

        return videos;
    }

    /** 保存当前勾选的流类型到 uiState */
    function captureSelectedStreams(container, videos) {
        if (!container) { // 容器不存在
            return;
        }

        const checked = container.querySelectorAll('input[name="stream_select"]:checked');
        uiState.selectedStreamKeys = new Set(Array.from(checked).map(cb => {
            const index = parseInt(cb.getAttribute('data-index'), 10);
            const videoInfo = videos[index];
            return videoInfo ? buildStreamSelectionKey(videoInfo, cb.getAttribute('data-key')) : null;
        }).filter(Boolean));
    }

    /** 记录课程列表滚动位置 */
    function captureSelectionScroll(container) {
        if (!container) {
            return;
        }

        const selectionContainer = container.querySelector('#video-selection-container');
        uiState.selectionScrollTop = selectionContainer ? selectionContainer.scrollTop : 0;
    }

    /** 恢复课程列表滚动位置 */
    function restoreSelectionScroll(container) {
        if (!container) {
            return;
        }

        const selectionContainer = container.querySelector('#video-selection-container');
        if (selectionContainer) {
            selectionContainer.scrollTop = uiState.selectionScrollTop;
        }
    }

    /** 记录状态区滚动位置 */
    function captureStatusScroll(container) {
        if (!container) {
            return;
        }

        const statusContainer = container.querySelector('#download-status-list');
        uiState.statusScrollTop = statusContainer ? statusContainer.scrollTop : 0;
    }

    /** 恢复状态区滚动位置 */
    function restoreStatusScroll(container) {
        if (!container) {
            return;
        }

        const statusContainer = container.querySelector('#download-status-list');
        if (statusContainer) {
            statusContainer.scrollTop = uiState.statusScrollTop;
        }
    }

    /** 统计当前已选流数量 */
    function countSelectedStreams(videos) {
        let count = 0;
        videos.forEach(video => {
            STREAM_TYPES.forEach(stream => {
                if (uiState.selectedStreamKeys.has(buildStreamSelectionKey(video, stream.key))) {
                    count++;
                }
            });
        });
        return count;
    }

    /** 判断指定流类型是否已经全部选中 */
    function areAllTargetStreamsSelected(videos, streamKeys) {
        return videos.length > 0 && videos.every(video => (
            streamKeys.every(streamKey => uiState.selectedStreamKeys.has(buildStreamSelectionKey(video, streamKey)))
        ));
    }

    /** 切换指定流类型的全选/取消全选，保留其它流的当前选择 */
    function toggleQuickSelection(videos, streamKeys) {
        const shouldCancel = areAllTargetStreamsSelected(videos, streamKeys);
        videos.forEach(video => {
            streamKeys.forEach(streamKey => {
                const selectionKey = buildStreamSelectionKey(video, streamKey);
                if (shouldCancel) {
                    uiState.selectedStreamKeys.delete(selectionKey);
                } else {
                    uiState.selectedStreamKeys.add(selectionKey);
                }
            });
        });
    }

    /** 同步快捷按钮的选择/取消文案 */
    function updateQuickSelectionButtons(container, videos) {
        const buttons = container.querySelectorAll('[data-action="quick-select"]');
        buttons.forEach(button => {
            const action = QUICK_SELECT_ACTIONS.find(item => item.key === button.getAttribute('data-quick-key'));
            if (!action) {
                return;
            }

            const isActive = areAllTargetStreamsSelected(videos, action.streamKeys);
            const label = button.querySelector('[data-role="quick-label"]');
            if (label) {
                label.textContent = isActive ? action.cancelLabel : action.selectLabel;
            }
            button.classList.toggle('is-active', isActive);
            button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });
    }

    /** 生成快捷选择按钮 HTML */
    function buildQuickActionsHtml(videos) {
        const disabled = videos.length === 0 ? 'disabled' : '';
        return QUICK_SELECT_ACTIONS.map(action => {
            const isActive = areAllTargetStreamsSelected(videos, action.streamKeys);
            const label = isActive ? action.cancelLabel : action.selectLabel;
            return `
            <button type="button"
                class="course-helper__quick-select${isActive ? ' is-active' : ''}"
                data-action="quick-select"
                data-quick-key="${action.key}"
                data-stream-keys="${action.streamKeys.join(',')}"
                aria-pressed="${isActive ? 'true' : 'false'}"
                ${disabled}>
                ${iconSvg(action.icon)}
                <span data-role="quick-label">${label}</span>
            </button>
        `;
        }).join('');
    }

    /** 生成课程勾选列表 HTML */
    function buildVideoListHtml(videos) {
        if (videos.length === 0) { // 列表为空
            return '<div class="course-helper__empty">当前页面还没有可提取的课程回放列表，等待页面加载或切换分页后会自动同步。</div>';
        }

        return videos.map((video, index) => {
            const streamOptions = STREAM_TYPES.map(type => {
                const checked = uiState.selectedStreamKeys.has(buildStreamSelectionKey(video, type.key)) ? 'checked' : '';
                return `
                    <label class="course-helper__stream">
                        <input type="checkbox" name="stream_select"
                            data-index="${index}"
                            data-key="${type.key}"
                            data-name="${type.name}"
                            ${checked}>
                        ${iconSvg(type.icon)}
                        <span>${type.name}</span>
                    </label>
                `;
            }).join('');

            return `
                <div class="course-helper__course">
                    <div>
                        <div class="course-helper__course-title" title="${escapeHtml(video.courseName)}">${escapeHtml(video.courseName)}</div>
                        <div class="course-helper__course-meta">rpId: ${escapeHtml(video.id1)} · courseId: ${escapeHtml(video.id2)}</div>
                    </div>
                    <div class="course-helper__stream-group">${streamOptions}</div>
                </div>
            `;
        }).join('');
    }

    /** 生成完整面板 HTML（折叠+展开） */
    function buildPanelMarkup(videos) {
        const selectedCount = countSelectedStreams(videos);
        const summaryText = videos.length > 0 ? `${videos.length} 门课 / 已选 ${selectedCount} 路` : '等待课程列表';
        const quickActionsHtml = buildQuickActionsHtml(videos);
        const videoListHtml = buildVideoListHtml(videos);

        return `
            <div class="course-helper__folded" data-action="toggle-panel">
                <div class="course-helper__folded-badge">${iconSvg('download', 'course-helper__icon--lg')}</div>
                <div class="course-helper__folded-copy">
                    <span class="course-helper__folded-title">轻松下载 V${CURRENT_VERSION}</span>
                    <span class="course-helper__folded-meta">${summaryText}</span>
                </div>
            </div>
            <div class="course-helper__expanded">
                <div class="course-helper__shell">
                    <section class="course-helper__hero">
                        <div class="course-helper__brand">
                            <div class="course-helper__brand-mark">${iconSvg('video', 'course-helper__icon--lg')}</div>
                            <div>
                                <span class="course-helper__eyebrow">LIGHT COURSE TOOL</span>
                                <h3 class="course-helper__title">轻松下载课程回放</h3>
                                <p class="course-helper__subtitle">轻量清爽，快速选流、排序队列、批量下载。</p>
                            </div>
                        </div>
                        <button type="button" class="course-helper__collapse" id="expanded-header" aria-label="收起面板">${iconSvg('chevronUp')}</button>
                    </section>
                    <div class="course-helper__main">
                        <section class="course-helper__section">
                            <div class="course-helper__section-head">
                                <div>
                                    <h4 class="course-helper__section-title">课程选择</h4>
                                    <p class="course-helper__section-hint">快捷按钮支持全选与取消全选，也可以继续逐项微调。</p>
                                </div>
                            </div>
                            <div class="course-helper__quick-actions">${quickActionsHtml}</div>
                            <div id="video-selection-container" class="course-helper__selection">${videoListHtml}</div>
                            <button id="submit-download-btn" class="course-helper__submit" type="button">
                                ${iconSvg('download')}
                                <span>生成下载队列</span>
                            </button>
                        </section>
                        <section class="course-helper__status-shell">
                            <div class="course-helper__section-head">
                                <div>
                                    <h4 class="course-helper__section-title">任务状态</h4>
                                    <p class="course-helper__section-hint">未下载任务可拖拽排序，完成后自动沉到底部。</p>
                                </div>
                            </div>
                            <div class="course-helper__metrics">
                                <div class="course-helper__metric">
                                    <span class="course-helper__metric-label">课程</span>
                                    <span class="course-helper__metric-value" data-role="course-count">${videos.length}</span>
                                </div>
                                <div class="course-helper__metric">
                                    <span class="course-helper__metric-label">已选</span>
                                    <span class="course-helper__metric-value" data-role="selected-count">${selectedCount}</span>
                                </div>
                                <div class="course-helper__metric">
                                    <span class="course-helper__metric-label">状态</span>
                                    <span class="course-helper__metric-value" data-role="panel-state">${videos.length > 0 ? '就绪' : '等待'}</span>
                                </div>
                            </div>
                            <button id="start-download-btn" class="course-helper__queue-start" type="button" hidden>
                                ${iconSvg('bolt')}
                                <span>按当前顺序开始下载</span>
                            </button>
                            <ul id="download-status-list" class="course-helper__status-list">
                                <li class="course-helper__status-placeholder">等待生成下载队列...</li>
                            </ul>
                        </section>
                    </div>
                </div>
            </div>
        `;
    }

    /** 切换面板展开/折叠状态 */
    function setPanelExpanded(container, expanded) {
        uiState.isExpanded = expanded;
        container.classList.toggle('is-expanded', expanded);
    }

    /** 更新面板摘要数字（课程数/已选流数） */
    function updatePanelSummary(container, videos) {
        if (!container) { // 容器不存在
            return;
        }

        const selectedCount = countSelectedStreams(videos);
        const foldedMeta = container.querySelector('.course-helper__folded-meta');
        const courseCount = container.querySelector('[data-role="course-count"]');
        const selectedCountNode = container.querySelector('[data-role="selected-count"]');
        const panelState = container.querySelector('[data-role="panel-state"]');

        if (foldedMeta) {
            foldedMeta.textContent = videos.length > 0 ? `${videos.length} 门课 / 已选 ${selectedCount} 路` : '等待课程列表';
        }

        if (courseCount) {
            courseCount.textContent = String(videos.length);
        }

        if (selectedCountNode) {
            selectedCountNode.textContent = String(selectedCount);
        }

        if (panelState) {
            panelState.textContent = videos.length > 0 ? '就绪' : '等待';
        }

        updateQuickSelectionButtons(container, videos);
    }

    /** 绑定面板点击、勾选、提交等事件 */
    function bindPanelEvents(container, videos) {
        const foldedHeader = container.querySelector('[data-action="toggle-panel"]');
        const expandedHeader = container.querySelector('#expanded-header');
        const submitButton = container.querySelector('#submit-download-btn');
        const startDownloadButton = container.querySelector('#start-download-btn');
        const selectionContainer = container.querySelector('#video-selection-container');
        const quickButtons = container.querySelectorAll('[data-action="quick-select"]');

        if (foldedHeader) {
            foldedHeader.addEventListener('click', function() {
                setPanelExpanded(container, true);
            });
        }

        if (expandedHeader) {
            expandedHeader.addEventListener('click', function(event) {
                event.stopPropagation();
                setPanelExpanded(container, false);
            });
        }

        if (selectionContainer) {
            selectionContainer.addEventListener('change', function(event) {
                if (event.target && event.target.matches('input[name="stream_select"]')) {
                    captureSelectedStreams(container, videos);
                    updatePanelSummary(container, videos);
                }
            });
        }

        quickButtons.forEach(button => {
            button.addEventListener('click', function(event) {
                event.stopPropagation();
                const streamKeys = (button.getAttribute('data-stream-keys') || '').split(',').filter(Boolean);
                toggleQuickSelection(videos, streamKeys);

                const checkboxes = container.querySelectorAll('input[name="stream_select"]');
                checkboxes.forEach(cb => {
                    const index = parseInt(cb.getAttribute('data-index'), 10);
                    const videoInfo = videos[index];
                    cb.checked = videoInfo
                        ? uiState.selectedStreamKeys.has(buildStreamSelectionKey(videoInfo, cb.getAttribute('data-key')))
                        : false;
                });
                updatePanelSummary(container, videos);
            });
        });

        if (submitButton) {
            submitButton.addEventListener('click', function(event) {
                event.stopPropagation();
                if (uiState.isDownloading) {
                    return;
                }
                captureSelectedStreams(container, videos);

                const checkboxes = container.querySelectorAll('input[name="stream_select"]:checked');
                const selectedStreams = [];
                const statusList = container.querySelector('#download-status-list');
                if (!statusList) {
                    return;
                }

                if (checkboxes.length === 0) { // 未选任何流
                    statusList.innerHTML = `<li class="course-helper__status-placeholder" style="color:${THEME_COLORS.error};">请选择至少一个视频流进行下载。</li>`;
                    return;
                }

                checkboxes.forEach(cb => {
                    const index = parseInt(cb.getAttribute('data-index'), 10);
                    selectedStreams.push({
                        videoInfo: videos[index],
                        streamKey: cb.getAttribute('data-key'),
                        streamName: cb.getAttribute('data-name'),
                    });
                });

                startBatchDownload(selectedStreams);
            });
        }

        if (startDownloadButton) {
            startDownloadButton.addEventListener('click', function(event) {
                event.stopPropagation();
                startQueuedDownload();
            });
        }
    }

    /** 获取或创建面板根容器 */
    function ensurePanelContainer() {
        let container = document.getElementById(PANEL_ID);
        if (!container) {
            container = document.createElement('div');
            container.id = PANEL_ID;
            document.body.appendChild(container);
        }
        return container;
    }

    /** 移除已失效课程的勾选状态 */
    function pruneSelectedStreams(videos) {
        const validKeys = new Set();
        videos.forEach(video => {
            STREAM_TYPES.forEach(stream => {
                validKeys.add(buildStreamSelectionKey(video, stream.key));
            });
        });
        uiState.selectedStreamKeys = new Set(Array.from(uiState.selectedStreamKeys).filter(key => validKeys.has(key)));
    }

    /** 重绘整个下载面板 UI */
    function renderUI(videos, options = {}) {
        const preserveSelections = options.preserveSelections !== false;
        const preserveSignature = options.preserveSignature === true;
        ensurePanelStyles();
        const container = ensurePanelContainer();

        if (!preserveSelections) { // 不保留勾选
            uiState.selectedStreamKeys = new Set();
        }

        pruneSelectedStreams(videos);
        captureSelectionScroll(container);
        captureStatusScroll(container);
        container.innerHTML = buildPanelMarkup(videos);
        bindPanelEvents(container, videos);
        setPanelExpanded(container, uiState.isExpanded);
        restoreSelectionScroll(container);
        restoreStatusScroll(container);

        uiState.videos = videos;
        if (!preserveSignature) { // 更新签名
            uiState.lastVideoSignature = buildVideoSignature(videos);
        }
    }

    /** 检测课程列表变化并刷新 UI */
    function refreshUI(force = false) {
        const videos = extractVideoInfo();
        const signature = buildVideoSignature(videos);

        if (!force && signature === uiState.lastVideoSignature) { // 列表未变
            return;
        }

        renderUI(videos, { preserveSelections: true, preserveSignature: true });
        uiState.lastVideoSignature = signature;
    }

    /** 防抖调度 UI 刷新 */
    function scheduleUIRefresh() {
        if (uiState.refreshTimer) { // 取消旧定时器
            clearTimeout(uiState.refreshTimer);
        }

        uiState.refreshTimer = setTimeout(function() {
            uiState.refreshTimer = null;
            refreshUI();
        }, REFRESH_DELAY);
    }

    /** 监听 DOM 变化，分页/异步刷新后同步课程列表 */
    function initializeVideoListObserver() {
        if (uiState.observerInitialized || typeof MutationObserver === 'undefined') { // 已初始化或无 API
            return;
        }

        const observer = new MutationObserver(function(mutations) {
            const shouldRefresh = mutations.some(function(mutation) {
                const target = mutation.target;
                if (target instanceof Element && target.closest(`#${PANEL_ID}`)) { // 面板内部变化
                    return false;
                }

                return true;
            });

            if (shouldRefresh) { // 页面课程区变化
                scheduleUIRefresh();
            }
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true,
            characterData: true,
        });

        uiState.observerInitialized = true;
        console.log('课程列表动态刷新观察已启用。');
    }

    /** 根据当前勾选生成可拖拽的下载队列 */
    async function startBatchDownload(selectedStreams) {
        const downloadStatusList = document.getElementById('download-status-list');
        if (!downloadStatusList) { // DOM 缺失
            return;
        }

        renderDownloadQueue(selectedStreams);
    }

    /** 按当前队列顺序串行下载，已完成任务自动沉到底部 */
    async function startQueuedDownload() {
        const downloadStatusList = document.getElementById('download-status-list');
        const submitBtn = document.getElementById('submit-download-btn');
        const startBtn = document.getElementById('start-download-btn');
        if (!downloadStatusList || !submitBtn || !startBtn || uiState.isDownloading) { // DOM 缺失或已在下载
            return;
        }

        if (uiState.downloadTasks.length === 0) { // 无队列
            downloadStatusList.innerHTML = `<li class="course-helper__status-placeholder" style="color:${THEME_COLORS.error};">请先生成下载队列。</li>`;
            return;
        }

        uiState.isDownloading = true;
        submitBtn.disabled = true;
        startBtn.disabled = true;
        const startLabel = startBtn.querySelector('span');
        if (startLabel) {
            startLabel.textContent = '下载进行中...';
        }

        while (true) {
            syncDownloadTaskOrderFromDom(downloadStatusList);
            const task = uiState.downloadTasks.find(item => item.state === 'pending');
            if (!task) {
                break;
            }

            setQueueTaskState(task, 'running');
            updatePendingQueueOrderLabels(downloadStatusList);
            updateStatus(task.statusElement, '准备开始下载...', 'info');
            const success = await handleStreamDownload(task.stream, task.statusElement);
            setQueueTaskState(task, success ? 'done' : 'failed');
            downloadStatusList.appendChild(task.item);
            updatePendingQueueOrderLabels(downloadStatusList);
        }

        uiState.isDownloading = false;
        submitBtn.disabled = false;
        startBtn.hidden = true;
        startBtn.disabled = false;

        const finalStatus = document.createElement('li');
        finalStatus.className = 'course-helper__status-final';
        finalStatus.textContent = '--- 所有任务处理完毕 ---';
        downloadStatusList.appendChild(finalStatus);
    }

    /** 拦截回放入口点击，绕过权限限制直接打开 */
    function setupReplayAccessInterceptor() {
        if (uiState.replayInterceptorInitialized) { // 已启用
            return;
        }

        document.addEventListener('click', function(event) {
            const target = event.target;
            if (!(target instanceof Element)) { // 非元素节点
                return;
            }

            const trigger = target.closest(REPLAY_SELECTOR);
            if (!trigger || trigger.closest(`#${PANEL_ID}`)) { // 非回放按钮或在面板内
                return;
            }

            const params = parseReplayParams(trigger.getAttribute('onclick'));
            if (!params) { // 解析失败
                return;
            }

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
            window.open(buildReplayUrl(params.rpId, params.courseId, params.courseNum, params.fzId));
        }, true);

        uiState.replayInterceptorInitialized = true;
        console.log('回放入口点击拦截已启用。');
    }

    /** 覆盖 getStuControlType，强制放行回放权限 */
    function applyMonkeyPatch() {
        if (typeof window.getStuControlType !== 'function') { // 函数未加载
            if (attempts < MAX_ATTEMPTS) { // 继续重试
                attempts++;
                setTimeout(applyMonkeyPatch, 100);
                return;
            }
            console.error('无法找到或覆盖 getStuControlType 函数。');
            return;
        }

        window.getStuControlType = function(rpId, courseId, courseNum, fzId) {
            const url = buildReplayUrl(rpId, courseId, courseNum, fzId);
            window.open(url);
        };

        console.log('getStuControlType 函数已成功覆盖，回放权限已开启。');
    }

    /** 绑定左右方向键快进/快退 10 秒 */
    function setupVideoHotkeys() {
        function handleKeydown(event) {
            const target = event.target;
            const tagName = target && target.tagName ? target.tagName.toLowerCase() : '';
            if (tagName === 'input' || tagName === 'textarea' || (target && target.isContentEditable)) { // 输入框内不拦截
                return;
            }

            const video = document.querySelector(VIDEO_SELECTOR);
            if (!video) { // 无播放器
                return;
            }

            let newTime = null;
            switch (event.key) {
                case 'ArrowLeft':
                    newTime = video.currentTime - SKIP_AMOUNT;
                    event.preventDefault();
                    break;
                case 'ArrowRight':
                    newTime = video.currentTime + SKIP_AMOUNT;
                    event.preventDefault();
                    break;
                default:
                    return;
            }

            if (newTime !== null) {
                video.currentTime = Math.max(0, Math.min(newTime, video.duration));
            }
        }

        window.addEventListener('keydown', handleKeydown, true);
        console.log(`视频播放器快捷键功能已启用 (左/右箭头快进/快退 ${SKIP_AMOUNT} 秒)。`);
    }

    /** 脚本入口：初始化回放绕过、面板、快捷键 */
    function main() {
        applyMonkeyPatch();
        setupReplayAccessInterceptor();
        setupVideoHotkeys();
        refreshUI(true);
        initializeVideoListObserver();
    }

    main();
})();
