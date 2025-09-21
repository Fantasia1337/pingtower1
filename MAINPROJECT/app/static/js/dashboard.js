export class MetricsDashboard {
    constructor(serviceId) {
        this.serviceId = serviceId;
        this.logs = []; // {timestamp, ok, responseTime}
        this.visible = true;
        this.timeRange = 15; // мин по умолчанию
        this.createDOM();
        this.fetchHistory(); // Загружаем историю при создании
    }

    async fetchHistory() {
        try {
            const res = await fetch(`/services/${this.serviceId}/history`);
            if (res.ok) {
                this.logs = await res.json();
                this.renderCharts();
                this.renderIncidents();
            }
        } catch (err) {
            console.error('Ошибка загрузки истории:', err);
        }
    }

    createDOM() {
        // Проверяем, существует ли уже дашборд
        if (document.getElementById(`dashboard-${this.serviceId}`)) {
            this.container = document.getElementById(`dashboard-${this.serviceId}`);
            return;
        }

        this.container = document.createElement('div');
        this.container.className = 'card dashboard-card';
        this.container.id = `dashboard-${this.serviceId}`;
        this.container.innerHTML = `
            <div class="dashboard-header">
                <h3>Сервис ${this.serviceId}</h3>
                <button class="toggle-btn">Скрыть графики</button>
            </div>
            <div class="dashboard-controls">
                <label>Период:
                    <select class="time-range">
                        <option value="5">5 мин</option>
                        <option value="15" selected>15 мин</option>
                        <option value="30">30 мин</option>
                    </select>
                </label>
            </div>
            <div class="charts-container">
                <canvas id="uptimeChart-${this.serviceId}" height="120"></canvas>
                <canvas id="responseChart-${this.serviceId}" height="120"></canvas>
            </div>
            <div id="incidents-${this.serviceId}" class="incident-log">
                <strong>Инциденты:</strong>
                <p>Нет инцидентов</p>
            </div>
        `;
        document.body.appendChild(this.container);

        // ==== кнопка скрытия ====
        this.container.querySelector('.toggle-btn').addEventListener('click', () => {
            this.visible = !this.visible;
            const charts = this.container.querySelector('.charts-container');
            charts.style.display = this.visible ? 'flex' : 'none';
            this.container.querySelector('.toggle-btn').textContent = this.visible
                ? 'Скрыть графики'
                : 'Показать графики';
        });

        // ==== селектор времени ====
        this.container.querySelector('.time-range').addEventListener('change', (e) => {
            this.timeRange = parseInt(e.target.value, 10);
            this.renderCharts();
        });

        // ==== инициализация графиков ====
        const ctxUptime = document.getElementById(`uptimeChart-${this.serviceId}`).getContext('2d');
        this.uptimeChart = new Chart(ctxUptime, {
            type: 'doughnut',
            data: {
                labels: ['UP', 'DOWN'],
                datasets: [{ data: [100, 0], backgroundColor: ['#4caf50', '#f44336'] }]
            },
            options: {
                plugins: {
                    legend: { position: 'bottom' },
                    title: {
                        display: true,
                        text: 'Аптайм'
                    }
                }
            }
        });

        const ctxResponse = document.getElementById(`responseChart-${this.serviceId}`).getContext('2d');
        this.responseChart = new Chart(ctxResponse, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Время отклика (ms)',
                    data: [],
                    borderColor: '#ff9800',
                    backgroundColor: 'rgba(255,152,0,0.2)',
                    tension: 0.3
                }]
            },
            options: {
                scales: {
                    y: { beginAtZero: true }
                },
                plugins: {
                    title: {
                        display: true,
                        text: 'Время отклика'
                    }
                }
            }
        });
    }

    update(ok, lastCheck, responseTime) {
        // Если responseTime не передан, генерируем случайное значение
        if (responseTime === undefined || responseTime === null) {
            responseTime = Math.floor(Math.random() * 300 + 100);
        }

        this.logs.push({ timestamp: lastCheck, ok, responseTime });

        // фильтруем по диапазону времени (оставляем данные за последние 24 часа)
        const cutoff = Date.now() - 24 * 60 * 60 * 1000;
        this.logs = this.logs.filter(l => new Date(l.timestamp).getTime() >= cutoff);

        this.renderCharts();
        this.renderIncidents();
    }

    renderCharts() {
        if (!this.uptimeChart || !this.responseChart) return;

        // Фильтруем логи по выбранному временному диапазону
        const cutoff = Date.now() - this.timeRange * 60 * 1000;
        const filteredLogs = this.logs.filter(l => new Date(l.timestamp).getTime() >= cutoff);

        if (filteredLogs.length === 0) {
            this.uptimeChart.data.datasets[0].data = [100, 0];
            this.uptimeChart.update();

            this.responseChart.data.labels = [];
            this.responseChart.data.datasets[0].data = [];
            this.responseChart.update();
            return;
        }

        const total = filteredLogs.length;
        const upCount = filteredLogs.filter(l => l.ok).length;
        const uptime = total > 0 ? (upCount / total) * 100 : 0;

        this.uptimeChart.data.datasets[0].data = [uptime, 100 - uptime];
        this.uptimeChart.update();

        this.responseChart.data.labels = filteredLogs.map(l => {
            const date = new Date(l.timestamp);
            return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
        });
        this.responseChart.data.datasets[0].data = filteredLogs.map(l => l.responseTime);
        this.responseChart.update();
    }

    renderIncidents() {
        const container = document.getElementById(`incidents-${this.serviceId}`);
        if (!container) return;

        container.innerHTML = '<strong>Инциденты:</strong>';
        const downs = this.logs.filter(l => !l.ok);
        if (downs.length === 0) {
            container.innerHTML += '<p>Нет инцидентов</p>';
            return;
        }
        downs.forEach(log => {
            const p = document.createElement('p');
            p.textContent = `❗ ${new Date(log.timestamp).toLocaleString()}`;
            container.appendChild(p);
        });
    }
}