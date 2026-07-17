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

            if (data.error) {
                showError(data.error);
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
        const kpis = data.kpis || {};

        // KPIs
        document.getElementById('kpi-spend').textContent = formatMoney(kpis.spend || 0);
        document.getElementById('kpi-impressions').textContent = formatNumber(kpis.impressions || 0);
        document.getElementById('kpi-clicks').textContent = formatNumber(kpis.clicks || 0);
        document.getElementById('kpi-ctr').textContent = formatPercent(kpis.ctr || 0);
        document.getElementById('kpi-cpc').textContent = formatMoney(kpis.cpc || 0);
        document.getElementById('kpi-reach').textContent = formatNumber(kpis.reach || 0);
        document.getElementById('kpi-frequency').textContent = formatNumber(kpis.frequency || 0);

        // Funnel
        document.getElementById('funnel-impressions').textContent = formatNumber(kpis.impressions || 0);
        document.getElementById('funnel-clicks').textContent = formatNumber(kpis.clicks || 0);
        document.getElementById('funnel-ctr').textContent = 'CTR: ' + formatPercent(kpis.ctr || 0);

        // Gráfico diario
        renderDailyChart(data.daily || []);

        // Gráfico de placement
        renderPlacementChart(data.placements || []);

        // Tablas
        renderTable('table-campaigns', data.campaigns || [], ['campaign_name', 'spend', 'impressions', 'clicks', 'ctr']);
        renderTable('table-ads', data.ads || [], ['campaign_name', 'ad_name', 'spend', 'impressions', 'clicks', 'ctr']);
    };

    const renderDailyChart = (daily) => {
        const ctx = document.getElementById('chart-daily').getContext('2d');
        const labels = daily.map(d => d.date);
        const spendData = daily.map(d => d.spend || 0);
        const impressionsData = daily.map(d => d.impressions || 0);
        const clicksData = daily.map(d => d.clicks || 0);

        if (dailyChart) {
            dailyChart.destroy();
        }

        dailyChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Spend',
                        data: spendData,
                        backgroundColor: '#1877f2',
                        yAxisID: 'y-spend',
                    },
                    {
                        label: 'Impressions',
                        data: impressionsData,
                        backgroundColor: '#42b72a',
                        yAxisID: 'y-metrics',
                    },
                    {
                        label: 'Clicks',
                        data: clicksData,
                        backgroundColor: '#ffcc00',
                        yAxisID: 'y-metrics',
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    'y-spend': {
                        type: 'linear',
                        display: true,
                        position: 'left',
                        title: { display: true, text: 'Spend' },
                    },
                    'y-metrics': {
                        type: 'linear',
                        display: true,
                        position: 'right',
                        grid: { drawOnChartArea: false },
                        title: { display: true, text: 'Impressions / Clicks' },
                    },
                },
            },
        });
    };

    const renderPlacementChart = (placements) => {
        const ctx = document.getElementById('chart-placement').getContext('2d');
        const labels = placements.map(p => p.publisher_platform || 'Desconocido');
        const data = placements.map(p => p.impressions || 0);
        const colors = ['#1877f2', '#42b72a', '#ffcc00', '#e91e63', '#9c27b0'];

        if (placementChart) {
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
                plugins: {
                    legend: { position: 'bottom' },
                },
            },
        });
    };

    const renderTable = (tableId, rows, columns) => {
        const tbody = document.querySelector('#' + tableId + ' tbody');
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
        if (accountSelect.options.length > 1) {
            accountSelect.selectedIndex = 1;
        }

        document.getElementById('btn-refresh').addEventListener('click', fetchData);

        // Cargar automáticamente si hay cuenta
        if (accountSelect.value) {
            fetchData();
        }
    });
})();
