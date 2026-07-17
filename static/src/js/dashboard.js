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

    const TOOLTIPS = {
        spend: 'Gasto total en publicidad durante el período seleccionado.',
        impressions: 'Número de veces que se mostraron tus anuncios.',
        clicks: 'Clics que hicieron en el enlace de tu anuncio.',
        ctr: 'Click-Through Rate: porcentaje de impresiones que terminaron en clic.',
        cpc: 'Costo por clic: cuánto pagás en promedio por cada clic.',
        reach: 'Número de personas únicas que vieron tus anuncios.',
        frequency: 'Promedio de veces que cada persona vio tus anuncios.',
        placement: 'Distribución por plataforma (Facebook, Instagram, etc.).',
        daily: 'Evolución diaria de las métricas principales.',
        campaign: 'Resultados agrupados por campaña.',
        creative: 'Resultados agrupados por anuncio o creatividad.',
        funnel: 'Embudo de conversión: de impresiones a clics.',
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
        document.getElementById('dashboard-loading').classList.toggle('hidden', !show);
    };

    const showError = (msg) => {
        const el = document.getElementById('dashboard-error');
        el.textContent = msg || '';
        el.classList.toggle('hidden', !msg);
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
            const response = await fetch('/meta_reporting/dashboard/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(filters),
            });
            const data = await response.json();

            if (!response.ok || data.error) {
                showError(data.error || 'Error ' + response.status);
                return;
            }

            renderDashboard(data);
        } catch (err) {
            showError('Error de conexión: ' + err.message);
        } finally {
            showLoading(false);
        }
    };

    const renderDashboard = (data) => {
        if (typeof Chart === 'undefined') {
            showError('No se pudo cargar la librería de gráficos (Chart.js). Verificá tu conexión a internet y recargá la página.');
            return;
        }

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

        // Gráficos
        try {
            renderDailyChart(data.daily || []);
            renderPlacementChart(data.placements || []);
        } catch (e) {
            showError('Error al dibujar gráficos: ' + e.message);
        }

        // Tablas
        renderTable('table-campaigns', data.campaigns || [], ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr']);
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

    const renderDailyChart = (daily) => {
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

    // Inicialización
    document.addEventListener('DOMContentLoaded', () => {
        const accountSelect = document.getElementById('filter-account');
        if (accountSelect && accountSelect.options.length > 1) {
            accountSelect.selectedIndex = 1;
        }

        const btnRefresh = document.getElementById('btn-refresh');
        if (btnRefresh) {
            btnRefresh.addEventListener('click', fetchData);
        }

        if (accountSelect && accountSelect.value) {
            fetchData();
        }
    });
})();
