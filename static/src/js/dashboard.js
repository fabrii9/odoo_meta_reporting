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
        } catch (err) {
            console.error('[MetaDashboard] Error:', err);
            showError('Error de conexión: ' + err.message);
        } finally {
            showLoading(false);
        }
    };

    const renderDashboard = (data) => {
        const kpis = data.kpis || {};

        // KPIs
        setKpi('kpi-spend', formatMoney(kpis.spend || 0));
        setKpi('kpi-impressions', formatNumber(kpis.impressions || 0));
        setKpi('kpi-clicks', formatNumber(kpis.clicks || 0));
        setKpi('kpi-ctr', formatPercent(kpis.ctr || 0));
        setKpi('kpi-cpc', formatMoney(kpis.cpc || 0));
        setKpi('kpi-reach', formatNumber(kpis.reach || 0));
        setKpi('kpi-frequency', formatNumber(kpis.frequency || 0));

        // Funnel
        setText('funnel-impressions', formatNumber(kpis.impressions || 0));
        setText('funnel-clicks', formatNumber(kpis.clicks || 0));
        setText('funnel-ctr', 'CTR: ' + formatPercent(kpis.ctr || 0));

        // Gráficos (cada uno protegido para no romper todo)
        safeRender('rendimiento diario', () => renderDailyChart(data.daily || []));
        safeRender('ubicación', () => renderPlacementChart(data.placements || []));

        // Tablas
        renderTable('table-campaigns', data.campaigns || [], ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr']);
        renderTable('table-adsets', data.adsets || [], ['campaign_name', 'adset_name', 'spend', 'impressions', 'clicks', 'ctr']);
        renderTable('table-ads', data.ads || [], ['campaign_name', 'ad_name', 'spend', 'impressions', 'clicks', 'ctr']);
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
                } else if (['impressions', 'clicks'].includes(col)) {
                    td.textContent = formatNumber(value);
                    td.classList.add('numeric');
                } else {
                    td.textContent = value || '-';
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
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

        initTabs();

        if (accountSelect && accountSelect.value) {
            fetchData();
        }
    });
})();
