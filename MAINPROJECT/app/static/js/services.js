import { notificationManager } from './notifications.js';
import { MetricsDashboard } from './dashboard.js';

export class ServiceManager {
    constructor(listEl) {
        this.listEl = listEl;
        this.services = [];
        this.dashboards = {};
    }

    async fetchServices() {
        try {
            const res = await fetch('/services');
            if (!res.ok) throw new Error('Ошибка загрузки сервисов');
            this.services = await res.json();
            this.renderServices();
        } catch (err) {
            notificationManager.show(`Ошибка сети: ${err.message}`);
        }
    }

    renderServices() {
        this.listEl.innerHTML = '';
        this.services.forEach(service => {
            const row = document.createElement('tr');
            row.dataset.id = service.id;

            row.innerHTML = `
                <td>${service.name}</td>
                <td><a href="${service.url}" target="_blank">${service.url}</a></td>
                <td id="status-${service.id}"><span class="spinner"></span></td>
                <td id="lastcheck-${service.id}">—</td>
                <td><button class="recheck-btn">Проверить</button></td>
            `;
            row.querySelector('.recheck-btn').addEventListener('click', () => this.recheckService(service.id));
            this.listEl.appendChild(row);

            // Инициализируем дашборд только если его еще нет
            if (!this.dashboards[service.id]) {
                this.dashboards[service.id] = new MetricsDashboard(service.id);
            }
            this.fetchStatus(service.id);
        });
    }

    async fetchStatus(id) {
        const statusCell = document.getElementById(`status-${id}`);
        const lastCheckCell = document.getElementById(`lastcheck-${id}`);
        try {
            const res = await fetch(`/status/${id}`);
            if (!res.ok) throw new Error('Ошибка получения статуса');
            const data = await res.json();

            statusCell.innerHTML = '';
            statusCell.appendChild(this.getStatusElement(data.ok));
            lastCheckCell.textContent = data.ts ? new Date(data.ts).toLocaleString() : '—';

            // Обновляем дашборд
            if (this.dashboards[id]) {
                this.dashboards[id].update(data.ok, data.ts, data.latency_ms);
            }
        } catch (err) {
            statusCell.innerHTML = '';
            statusCell.appendChild(this.getStatusElement(null));
            lastCheckCell.textContent = '—';
        }
    }

    async recheckService(id) {
        const statusCell = document.getElementById(`status-${id}`);
        statusCell.innerHTML = '<span class="spinner"></span>';
        try {
            const res = await fetch(`/services/${id}/recheck`, { method: 'POST' });
            if (!res.ok) throw new Error('Ошибка проверки');
            await new Promise(r => setTimeout(r, 1500));
            this.fetchStatus(id);
        } catch (err) {
            notificationManager.show(`Ошибка проверки: ${err.message}`);
        }
    }

    getStatusElement(ok) {
        const statusClass = ok === true ? 'up' : ok === false ? 'down' : 'unknown';
        const statusText = ok === true ? 'UP' : ok === false ? 'DOWN' : '—';
        const span = document.createElement('span');
        span.className = `status-${statusClass}`;
        span.innerHTML = `<span class="status-dot"></span><strong>${statusText}</strong>`;
        return span;
    }
}