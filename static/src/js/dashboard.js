/* global Chart */
(function () {
    'use strict';

    const formatNumber = (num) => {
        if (num === null || num === undefined || isNaN(num)) return '-';
        return new Intl.NumberFormat('es-AR', { maximumFractionDigits: 2 }).format(num);
    };

    const formatMoney = (num) => {
        if (num === null || num === undefined || isNaN(num)) return '-';
        return '$ ' + formatNumber(num);
    };

    const formatPercent = (num) => {
        if (num === null || num === undefined || isNaN(num)) return '-';
        return formatNumber(num) + '%';
    };

    let dailyChart = null;
    let placementChart = null;
    let ratiosChart = null;
    let roasChart = null;
    let topRoasChart = null;
    let spendRevenueChart = null;
    let lastData = null;

    const getFilters = () => {
        return {
            account_id: document.getElementById('filter-account').value,
            campaign_name: document.getElementById('filter-campaign').value.trim() || null,
            date_from: document.getElementById('filter-date-from').value,
            date_to: document.getElementById('filter-date-to').value,
        };
    };

    const showLoading = (show) => {
        const el = document.getElementById('dashboard-loading');
        if (el) el.classList.toggle('hidden', !show);
    };

    const showError = (msg) => {
        const el = document.getElementById('dashboard-error');
        if (el) {
            el.textContent = msg || '';
            el.classList.toggle('hidden', !msg);
        }
    };

    const fetchData = async () => {
        const filters = getFilters();
        if (!filters.account_id) {
            showError('Seleccioná una cuenta para ver el dashboard.');
            return;
        }

        showLoading(true);
        showError('');

        try {
            console.log('[MetaDashboard] Fetching data...', filters);
            const response = await fetch('/meta_reporting/dashboard/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filters),
            });

            const contentType = response.headers.get('content-type') || '';
            let data;
            if (contentType.includes('application/json')) {
                data = await response.json();
            } else {
                const text = await response.text();
                console.error('[MetaDashboard] Respuesta no-JSON:', text.substring(0, 500));
                showError('Error del servidor: respuesta inesperada.');
                return;
            }

            console.log('[MetaDashboard] Data received:', data);

            if (!response.ok || data.error) {
                showError(data.error || 'Error ' + response.status);
                return;
            }

            renderDashboard(data);
            lastData = data;
        } catch (err) {
            console.error('[MetaDashboard] Error:', err);
            showError('Error de conexión: ' + err.message);
        } finally {
            showLoading(false);
        }
    };

    const renderDashboard = (data) => {
        const kpis = data.kpis || {};
        const prev = data.kpis_prev || {};

        // KPIs principales
        setKpi('kpi-spend', formatMoney(kpis.spend || 0));
        setKpi('kpi-impressions', formatNumber(kpis.impressions || 0));
        setKpi('kpi-clicks', formatNumber(kpis.clicks || 0));
        setKpi('kpi-ctr', formatPercent(kpis.ctr || 0));
        setKpi('kpi-cpc', formatMoney(kpis.cpc || 0));
        setKpi('kpi-cpm', formatMoney(kpis.cpm || 0));
        setKpi('kpi-reach', formatNumber(kpis.reach || 0));
        setKpi('kpi-frequency', formatNumber(kpis.frequency || 0));

        // Deltas vs período anterior (invert = true cuando bajar es bueno)
        setDelta('delta-spend', kpis.spend, prev.spend);
        setDelta('delta-impressions', kpis.impressions, prev.impressions);
        setDelta('delta-clicks', kpis.clicks, prev.clicks);
        setDelta('delta-ctr', kpis.ctr, prev.ctr);
        setDelta('delta-cpc', kpis.cpc, prev.cpc, true);
        setDelta('delta-cpm', kpis.cpm, prev.cpm, true);
        setDelta('delta-reach', kpis.reach, prev.reach);
        setDelta('delta-frequency', kpis.frequency, prev.frequency, true);

        // KPIs de conversión
        const conv = data.conversion_kpis || {};
        const convPrev = data.conversion_kpis_prev || {};
        setKpi('kpi-purchases', formatNumber(conv.purchases || 0));
        setKpi('kpi-purchase-value', formatMoney(conv.purchase_value || 0));
        setKpi('kpi-roas', formatNumber(conv.roas || 0));
        setKpi('kpi-cost-per-purchase', formatMoney(conv.cost_per_purchase || 0));
        setDelta('delta-purchases', conv.purchases, convPrev.purchases);
        setDelta('delta-roas', conv.roas, convPrev.roas);

        // Embudo dinámico
        safeRender('embudo', () => renderFunnel(data.funnel || []));

        // Gráficos (cada uno protegido para no romper todo)
        safeRender('rendimiento diario', () => renderDailyChart(data.daily || []));
        safeRender('ubicación', () => renderPlacementChart(data.placements || []));
        safeRender('ratios diarios', () => renderRatiosChart(data.ratio_daily || []));
        safeRender('roas diario', () => renderRoasChart(data.ratio_daily || []));
        safeRender('top campañas por roas', () => renderTopRoasChart(data.campaigns || []));
        safeRender('gasto vs revenue', () => renderSpendRevenueChart(data.campaigns || []));

        // Galería de creatividades
        safeRender('creatividades', () => renderCreatives(data.ads || []));

        // Tablas
        renderTable('table-campaigns', data.campaigns || [], ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr', 'roas']);
        renderTable('table-adsets', data.adsets || [], ['campaign_name', 'adset_name', 'spend', 'impressions', 'clicks', 'ctr']);
        renderTable('table-ads', data.ads || [], ['campaign_name', 'ad_name', 'spend', 'impressions', 'clicks', 'ctr', 'purchases']);
    };

    const setDelta = (id, current, previous, invert) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (current === null || current === undefined || !previous) {
            el.textContent = '';
            el.className = 'kpi-delta';
            return;
        }
        const pct = ((current - previous) / previous) * 100;
        if (!isFinite(pct)) {
            el.textContent = '';
            el.className = 'kpi-delta';
            return;
        }
        const up = pct >= 0;
        const good = invert ? !up : up;
        el.textContent = (up ? '▲ +' : '▼ ') + formatNumber(pct) + '% vs período anterior';
        el.className = 'kpi-delta ' + (good ? 'delta-good' : 'delta-bad');
    };

    const setKpi = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const setText = (id, value) => {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
    };

    const safeRender = (name, fn) => {
        try {
            fn();
        } catch (e) {
            console.error('[MetaDashboard] Error dibujando ' + name + ':', e);
        }
    };

    const renderDailyChart = (daily) => {
        if (typeof Chart === 'undefined') {
            console.warn('[MetaDashboard] Chart.js no está cargado, saltando gráfico diario.');
            return;
        }
        const canvas = document.getElementById('chart-daily');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const labels = daily.map(d => d.date ? d.date.substring(0, 10) : '');
        const spendData = daily.map(d => d.spend || 0);
        const impressionsData = daily.map(d => d.impressions || 0);
        const clicksData = daily.map(d => d.clicks || 0);

        if (dailyChart && typeof dailyChart.destroy === 'function') {
            dailyChart.destroy();
        }

        dailyChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Gasto', data: spendData, backgroundColor: '#1877f2' },
                    { label: 'Impresiones', data: impressionsData, backgroundColor: '#42b72a' },
                    { label: 'Clics', data: clicksData, backgroundColor: '#ffcc00' },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { position: 'bottom' },
                scales: {
                    yAxes: [{ ticks: { beginAtZero: true } }],
                    xAxes: [{ ticks: { autoSkip: false, maxRotation: 45, minRotation: 0 } }],
                },
            },
        });
    };

    const renderPlacementChart = (placements) => {
        if (typeof Chart === 'undefined') {
            console.warn('[MetaDashboard] Chart.js no está cargado, saltando gráfico de ubicación.');
            return;
        }
        const canvas = document.getElementById('chart-placement');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const labels = placements.map(p => p.publisher_platform || 'Desconocido');
        const data = placements.map(p => p.impressions || 0);
        const colors = ['#1877f2', '#42b72a', '#ffcc00', '#e91e63', '#9c27b0', '#00bcd4'];

        if (placementChart && typeof placementChart.destroy === 'function') {
            placementChart.destroy();
        }

        placementChart = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: data,
                    backgroundColor: colors,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { position: 'bottom' },
            },
        });
    };

    const renderTable = (tableId, rows, columns) => {
        const tbody = document.querySelector('#' + tableId + ' tbody');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (!rows.length) {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="' + columns.length + '" style="text-align:center;color:#65676b;">No hay datos</td>';
            tbody.appendChild(tr);
            return;
        }

        rows.forEach(row => {
            const tr = document.createElement('tr');
            columns.forEach(col => {
                const td = document.createElement('td');
                let value = row[col];
                if (['spend', 'cpc'].includes(col)) {
                    td.textContent = formatMoney(value);
                    td.classList.add('numeric');
                } else if (col === 'ctr') {
                    td.textContent = formatPercent(value);
                    td.classList.add('numeric');
                } else if (['impressions', 'clicks', 'purchases', 'roas'].includes(col)) {
                    td.textContent = value ? formatNumber(value) : '-';
                    td.classList.add('numeric');
                } else {
                    td.textContent = value || '-';
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
    };

    const renderRatiosChart = (daily) => {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById('chart-ratios');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const labels = daily.map(d => d.date ? d.date.substring(0, 10) : '');
        if (ratiosChart && typeof ratiosChart.destroy === 'function') {
            ratiosChart.destroy();
        }

        ratiosChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'CTR %',
                        data: daily.map(d => d.ctr || 0),
                        borderColor: '#1877f2',
                        backgroundColor: 'transparent',
                        yAxisID: 'y-ratio',
                        pointRadius: 2,
                    },
                    {
                        label: 'CPC',
                        data: daily.map(d => d.cpc || 0),
                        borderColor: '#e91e63',
                        backgroundColor: 'transparent',
                        yAxisID: 'y-money',
                        pointRadius: 2,
                    },
                    {
                        label: 'CPM',
                        data: daily.map(d => d.cpm || 0),
                        borderColor: '#9c27b0',
                        backgroundColor: 'transparent',
                        yAxisID: 'y-money',
                        pointRadius: 2,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { position: 'bottom' },
                scales: {
                    yAxes: [
                        { id: 'y-ratio', position: 'left', ticks: { beginAtZero: true } },
                        { id: 'y-money', position: 'right', ticks: { beginAtZero: true } },
                    ],
                    xAxes: [{ ticks: { autoSkip: true, maxRotation: 45 } }],
                },
            },
        });
    };

    const renderRoasChart = (daily) => {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById('chart-roas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const labels = daily.map(d => d.date ? d.date.substring(0, 10) : '');
        if (roasChart && typeof roasChart.destroy === 'function') {
            roasChart.destroy();
        }

        roasChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'ROAS',
                    data: daily.map(d => d.roas || null),
                    borderColor: '#42b72a',
                    backgroundColor: 'rgba(66, 183, 42, 0.1)',
                    fill: true,
                    spanGaps: true,
                    pointRadius: 2,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { position: 'bottom' },
                scales: {
                    yAxes: [{ ticks: { beginAtZero: true } }],
                    xAxes: [{ ticks: { autoSkip: true, maxRotation: 45 } }],
                },
            },
        });
    };

    const renderTopRoasChart = (campaigns) => {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById('chart-top-roas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const top = campaigns
            .filter(c => c.roas && c.roas > 0)
            .sort((a, b) => b.roas - a.roas)
            .slice(0, 5);

        if (topRoasChart && typeof topRoasChart.destroy === 'function') {
            topRoasChart.destroy();
        }

        if (!top.length) {
            topRoasChart = null;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }

        topRoasChart = new Chart(ctx, {
            type: 'horizontalBar',
            data: {
                labels: top.map(c => (c.campaign_name || '').substring(0, 35)),
                datasets: [{
                    label: 'ROAS',
                    data: top.map(c => c.roas),
                    backgroundColor: '#42b72a',
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { display: false },
                scales: {
                    xAxes: [{ ticks: { beginAtZero: true } }],
                },
            },
        });
    };

    const renderSpendRevenueChart = (campaigns) => {
        if (typeof Chart === 'undefined') return;
        const canvas = document.getElementById('chart-spend-revenue');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const top = campaigns
            .slice()
            .sort((a, b) => (b.spend || 0) - (a.spend || 0))
            .slice(0, 8);

        if (spendRevenueChart && typeof spendRevenueChart.destroy === 'function') {
            spendRevenueChart.destroy();
        }

        if (!top.length) {
            spendRevenueChart = null;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            return;
        }

        spendRevenueChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: top.map(c => (c.campaign_name || '').substring(0, 25)),
                datasets: [
                    { label: 'Gasto', data: top.map(c => c.spend || 0), backgroundColor: '#1877f2' },
                    { label: 'Revenue (gasto × ROAS)', data: top.map(c => (c.spend || 0) * (c.roas || 0)), backgroundColor: '#42b72a' },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                legend: { position: 'bottom' },
                scales: {
                    yAxes: [{ ticks: { beginAtZero: true } }],
                    xAxes: [{ ticks: { autoSkip: false, maxRotation: 45 } }],
                },
            },
        });
    };

    const renderFunnel = (steps) => {
        const container = document.getElementById('funnel');
        if (!container) return;
        container.innerHTML = '';

        if (!steps.length) {
            container.innerHTML = '<div style="color:#65676b;">No hay datos de embudo para este período.</div>';
            return;
        }

        steps.forEach((step, idx) => {
            if (idx > 0) {
                const arrow = document.createElement('div');
                arrow.className = 'funnel-arrow';
                arrow.textContent = '↓';
                container.appendChild(arrow);
            }
            const div = document.createElement('div');
            div.className = 'funnel-step funnel-step-' + idx;

            const label = document.createElement('span');
            label.className = 'funnel-label';
            label.textContent = step.label || '';
            div.appendChild(label);

            const value = document.createElement('span');
            value.className = 'funnel-value';
            value.textContent = formatNumber(step.count || 0);
            div.appendChild(value);

            const details = [];
            if (step.rate) details.push('Tasa: ' + formatPercent(step.rate));
            if (step.cost) details.push('Costo: ' + formatMoney(step.cost));
            if (details.length) {
                const rate = document.createElement('span');
                rate.className = 'funnel-rate';
                rate.textContent = details.join(' · ');
                div.appendChild(rate);
            }

            container.appendChild(div);
        });
    };

    const STATUS_LABELS = {
        ACTIVE: { label: 'Activo', cls: 'status-active' },
        PAUSED: { label: 'Pausado', cls: 'status-paused' },
        DELETED: { label: 'Eliminado', cls: 'status-off' },
        PENDING_REVIEW: { label: 'En revisión', cls: 'status-paused' },
        DISAPPROVED: { label: 'Rechazado', cls: 'status-off' },
        PREAPPROVED: { label: 'Pre-aprobado', cls: 'status-paused' },
        PENDING_BILLING_INFO: { label: 'Sin facturación', cls: 'status-off' },
        CAMPAIGN_PAUSED: { label: 'Campaña pausada', cls: 'status-paused' },
        ADSET_PAUSED: { label: 'Adset pausado', cls: 'status-paused' },
        ARCHIVED: { label: 'Archivado', cls: 'status-off' },
    };

    const renderCreatives = (ads) => {
        const grid = document.getElementById('creatives-grid');
        if (!grid) return;
        grid.innerHTML = '';

        const withImage = ads.filter(a => a.thumbnail_url || a.image_url);
        if (!withImage.length) {
            grid.innerHTML = '<div style="color:#65676b;padding:12px;">No hay creatividades con imagen. Sincronizá a nivel anuncio (Sincronizar todos los niveles) para traer los thumbnails.</div>';
            return;
        }

        // Activos primero, luego por gasto descendente
        const sorted = withImage.slice().sort((a, b) => {
            const aActive = (a.ad_status === 'ACTIVE') ? 0 : 1;
            const bActive = (b.ad_status === 'ACTIVE') ? 0 : 1;
            if (aActive !== bActive) return aActive - bActive;
            return (b.spend || 0) - (a.spend || 0);
        });

        sorted.slice(0, 48).forEach(ad => {
            const card = document.createElement('div');
            card.className = 'creative-card';

            const imgWrap = document.createElement('div');
            imgWrap.className = 'creative-img-wrap';

            const img = document.createElement('img');
            img.src = ad.thumbnail_url || ad.image_url;
            img.alt = ad.ad_name || 'anuncio';
            img.loading = 'lazy';
            img.onerror = () => { img.style.display = 'none'; };
            imgWrap.appendChild(img);

            // Badge de estado
            const st = STATUS_LABELS[ad.ad_status] || { label: ad.ad_status || 'Sin datos', cls: 'status-unknown' };
            const badge = document.createElement('span');
            badge.className = 'creative-status ' + st.cls;
            badge.textContent = st.label;
            imgWrap.appendChild(badge);

            card.appendChild(imgWrap);

            const body = document.createElement('div');
            body.className = 'creative-body';

            const name = document.createElement('div');
            name.className = 'creative-name';
            name.textContent = ad.ad_name || '-';
            name.title = ad.ad_name || '';
            body.appendChild(name);

            const campaign = document.createElement('div');
            campaign.className = 'creative-campaign';
            campaign.textContent = ad.campaign_name || '';
            campaign.title = ad.campaign_name || '';
            body.appendChild(campaign);

            const metrics = document.createElement('div');
            metrics.className = 'creative-metrics';
            metrics.innerHTML =
                '<span>Gasto: <b>' + formatMoney(ad.spend || 0) + '</b></span>' +
                '<span>Imp: <b>' + formatNumber(ad.impressions || 0) + '</b></span>' +
                '<span>Clics: <b>' + formatNumber(ad.clicks || 0) + '</b></span>' +
                '<span>CTR: <b>' + formatPercent(ad.ctr || 0) + '</b></span>' +
                (ad.purchases ? '<span>Compras: <b>' + formatNumber(ad.purchases) + '</b></span>' : '') +
                (ad.roas ? '<span>ROAS: <b>' + formatNumber(ad.roas) + '</b></span>' : '');
            body.appendChild(metrics);

            card.appendChild(body);
            grid.appendChild(card);
        });
    };

    // Exportar CSV de la pestaña activa
    const exportCSV = () => {
        if (!lastData) {
            showError('Primero cargá los datos con "Actualizar".');
            return;
        }
        const activeTab = document.querySelector('.tab-btn.active');
        const tab = activeTab ? activeTab.dataset.tab : 'campaigns';
        const configs = {
            campaigns: { key: 'campaigns', label: 'campanias', cols: ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr', 'roas'] },
            adsets: { key: 'adsets', label: 'adsets', cols: ['campaign_name', 'adset_name', 'spend', 'impressions', 'clicks', 'ctr'] },
            ads: { key: 'ads', label: 'anuncios', cols: ['campaign_name', 'ad_name', 'spend', 'impressions', 'clicks', 'ctr', 'purchases', 'roas'] },
        };
        const cfg = configs[tab] || configs.campaigns;
        const rows = lastData[cfg.key] || [];
        if (!rows.length) {
            showError('No hay datos para descargar en esta pestaña.');
            return;
        }
        showError('');

        const escapeCell = (v) => {
            if (v === null || v === undefined) return '';
            const s = String(v);
            return /[";\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
        };

        // Punto y coma como separador (Excel es-AR usa coma decimal)
        const lines = [cfg.cols.join(';')];
        rows.forEach(row => {
            lines.push(cfg.cols.map(c => escapeCell(row[c])).join(';'));
        });

        // BOM para que Excel abra el UTF-8 correctamente
        const blob = new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const filters = getFilters();
        const filename = 'meta_ads_' + cfg.label + '_' + filters.date_from + '_' + filters.date_to + '.csv';
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    };

    // Tabs
    const initTabs = () => {
        const tabBtns = document.querySelectorAll('.tab-btn');
        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const target = btn.dataset.tab;
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                document.querySelectorAll('.tab-content').forEach(content => {
                    content.classList.add('hidden');
                });
                const targetEl = document.getElementById('tab-' + target);
                if (targetEl) targetEl.classList.remove('hidden');
            });
        });
    };

    // Inicialización
    document.addEventListener('DOMContentLoaded', () => {
        console.log('[MetaDashboard] DOM ready. Chart.js loaded:', typeof Chart !== 'undefined');

        const accountSelect = document.getElementById('filter-account');
        if (accountSelect && accountSelect.options.length > 1) {
            accountSelect.selectedIndex = 1;
        }

        const btnRefresh = document.getElementById('btn-refresh');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', fetchData);
        }

        const btnDownload = document.getElementById('btn-download');
        if (btnDownload) {
            btnDownload.addEventListener('click', exportCSV);
        }

        initTabs();

        if (accountSelect && accountSelect.value) {
            fetchData();
        }
    });
})();
