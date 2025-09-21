// static/js/app.js
/**
 * @fileoverview Основной фронтенд PingTower с графиками, инцидентами и уведомлениями.
 */

import { apiCall } from './api.js';
import { notificationManager } from './notifications.js';

const serviceForm = document.getElementById('serviceForm');
const servicesList = document.getElementById('servicesList');
const emptyState = document.getElementById('emptyState');
const refreshButton = document.getElementById('refreshButton');
const statusFilter = document.getElementById('statusFilter');
const searchInput = document.getElementById('searchInput');

let services = []; // список сервисов
let serviceLogs = {}; // хранение логов падений для графиков
let serviceIncidents = {}; // хранение инцидентов для отображения

// --- Состояние UI ---
let currentSortBy = 'name'; // Поле для сортировки
let currentSortDirection = 'asc'; // Направление сортировки
let currentFilter = 'all'; // Фильтр по статусу
let currentSearchTerm = ''; // Поисковый запрос

// --- Управление видимостью графиков ---
const visibleCharts = new Set(); // Храним ID сервисов с открытыми графиками

// --- Форматирование дат ---
function formatDate(isoString) {
    if (!isoString) return '—';
    const date = new Date(isoString);
    return date.toLocaleString(); // Можно улучшить до "n сек назад"
}

// --- Элемент статуса ---
function getStatusElement(ok) {
    const statusClass = ok === true ? 'up' : ok === false ? 'down' : 'unknown';
    const statusText = ok === true ? 'UP' : ok === false ? 'DOWN' : '—';
    const dotClass = `status-dot-enhanced`;
    const span = document.createElement('span');
    span.className = `status-${statusClass}`;
    span.innerHTML = `<span class="${dotClass}"></span><strong>${statusText}</strong>`;
    return span;
}

// --- Отображение инцидентов ---
function renderIncidents(serviceId, incidents) {
    const incidentsContainer = document.getElementById(`incidents-${serviceId}`);
    if (!incidentsContainer) return;
    if (!incidents || incidents.length === 0) {
        incidentsContainer.innerHTML = '<p>Нет записей об инцидентах.</p>';
        return;
    }
    // Отображаем последние 5 инцидентов
    const lastIncidents = incidents.slice(-5).reverse(); // Последние 5, от новых к старым
    let incidentsHtml = '<ul>';
    lastIncidents.forEach(incident => {
        incidentsHtml += `<li><strong>${formatDate(incident.start)}</strong> - ${incident.end ? formatDate(incident.end) : 'Текущий инцидент'}</li>`;
    });
    incidentsHtml += '</ul>';
    incidentsContainer.innerHTML = incidentsHtml;
}

// --- Создание графика ---
function createChart(serviceId) {
    const canvas = document.getElementById(`chart-${serviceId}`);
    if (!canvas) {
        console.error(`Canvas not found for service ${serviceId}`);
        return null;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        console.error(`Context not available for canvas ${serviceId}`);
        return null;
    }

    // Установим размеры canvas явно
    // Убедимся, что родительский элемент имеет размеры
    const container = canvas.parentElement;
    if (container) {
        canvas.width = container.clientWidth || 400;
        canvas.height = container.clientHeight || 200; // Используем 200px как в CSS
    } else {
        canvas.width = 400;
        canvas.height = 200;
    }

    // Создаем tooltip элемент
    const tooltip = document.createElement('div');
    tooltip.className = 'chart-tooltip hidden';
    tooltip.id = `tooltip-${serviceId}`;
    document.body.appendChild(tooltip);
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Статус',
                data: [],
                borderColor: '#ff9800',
                backgroundColor: 'rgba(255, 152, 0, 0.1)',
                borderWidth: 2,
                pointRadius: 4,
                pointBackgroundColor: function(context) {
                    const value = context.dataset.data[context.dataIndex];
                    if (value === 1) return '#4caf50';
                    if (value === 0) return '#f44336';
                    return '#9e9e9e';
                },
                pointBorderColor: 'rgba(255, 255, 255, 0.8)',
                pointBorderWidth: 1,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: false, // Отключаем, так как мы задаём размеры вручную
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: false,
                    external: function(context) {
                        const tooltipEl = document.getElementById(`tooltip-${serviceId}`);
                        if (!tooltipEl) return;
                        const tooltipModel = context.tooltip;
                        if (tooltipModel.opacity === 0) {
                            tooltipEl.classList.add('hidden');
                            return;
                        }
                        if (tooltipModel.body) {
                            const dataIndex = tooltipModel.dataPoints[0].dataIndex;
                            const label = tooltipModel.labelColors[0].backgroundColor;
                            const value = context.chart.data.datasets[0].data[dataIndex];
                            const statusText = value === 1 ? 'UP' : value === 0 ? 'DOWN' : 'UNKNOWN';
                            tooltipEl.innerHTML = `
                                <div style="color: ${label}; font-weight: bold;">${statusText}</div>
                                <div>${context.chart.data.labels[dataIndex]}</div>
                            `;
                        }
                        const position = context.chart.canvas.getBoundingClientRect();
                        tooltipEl.style.left = position.left + window.pageXOffset + tooltipModel.caretX + 10 + 'px';
                        tooltipEl.style.top = position.top + window.pageYOffset + tooltipModel.caretY + 10 + 'px';
                        tooltipEl.classList.remove('hidden');
                    }
                }
            },
            scales: {
                y: {
                    min: 0,
                    max: 1,
                    grid: {
                        color: 'rgba(255, 255, 255, 0.05)',
                        drawBorder: false
                    },
                    ticks: {
                        callback: function(value) {
                            return value === 1 ? 'UP' : value === 0 ? 'DOWN' : '—';
                        },
                        color: 'rgba(255, 255, 255, 0.7)',
                        font: { size: 10 }
                    }
                },
                x: {
                    grid: {
                        display: false
                    },
                    ticks: {
                        autoSkip: true,
                        maxTicksLimit: 6,
                        color: 'rgba(255, 255, 255, 0.7)',
                        font: { size: 9 }
                    }
                }
            },
            animations: {
                tension: {
                    duration: 1000,
                    easing: 'linear'
                }
            }
        }
    });
}

// --- Переключение видимости графика ---
// Делаем функцию доступной глобально
window.toggleChart = function(serviceId) {
    const chartContent = document.getElementById(`chart-content-${serviceId}`);
    const toggleBtn = document.getElementById(`toggle-btn-${serviceId}`);
    if (!chartContent || !toggleBtn) return;
    if (chartContent.classList.contains('collapsed')) {
        chartContent.classList.remove('collapsed');
        toggleBtn.textContent = '−';
        visibleCharts.add(serviceId); // Отслеживаем открытые графики
        // Инициализируем график, если он еще не создан
        const service = services.find(s => s.id == serviceId);
        if (service && !service.chart) {
             service.chart = createChart(serviceId);
             if (service.chart) {
                 fetchStatus(serviceId); // Загружаем данные для графика
             }
        }
    } else {
        chartContent.classList.add('collapsed');
        toggleBtn.textContent = '+';
        visibleCharts.delete(serviceId); // Убираем из отслеживаемых
    }
};

// --- Фильтрация и сортировка ---
function applyFiltersAndSort() {
    let filteredServices = [...services];

    // Фильтрация
    if (currentFilter !== 'all') {
        filteredServices = filteredServices.filter(s => s.status === currentFilter);
    }
    if (currentSearchTerm) {
        const term = currentSearchTerm.toLowerCase();
        filteredServices = filteredServices.filter(s =>
            s.name.toLowerCase().includes(term) || s.url.toLowerCase().includes(term)
        );
    }

    // Сортировка (устойчивая)
    filteredServices.sort((a, b) => {
        let valA = a[currentSortBy];
        let valB = b[currentSortBy];

        // Обработка дат
        if (currentSortBy === 'lastCheck') {
            valA = valA ? new Date(valA) : new Date(0);
            valB = valB ? new Date(valB) : new Date(0);
        }
        // Обработка чисел (uptime)
        else if (currentSortBy === 'uptime') {
             valA = parseFloat(valA) || 0;
             valB = parseFloat(valB) || 0;
        }
        // Обработка строк
        else if (typeof valA === 'string') {
            return currentSortDirection === 'asc' ?
                valA.localeCompare(valB, undefined, { sensitivity: 'base' }) :
                valB.localeCompare(valA, undefined, { sensitivity: 'base' });
        }

        if (valA < valB) return currentSortDirection === 'asc' ? -1 : 1;
        if (valA > valB) return currentSortDirection === 'asc' ? 1 : -1;
        return 0; // Равны
    });

    return filteredServices;
}

// --- Отображение списка сервисов ---
function renderServices() {
    if (!servicesList) return;
    const filteredServices = applyFiltersAndSort();

    servicesList.innerHTML = '';
    if (filteredServices.length === 0) {
        if (emptyState) emptyState.classList.remove('hidden');
        return;
    }
    if (emptyState) emptyState.classList.add('hidden');

    filteredServices.forEach(service => {
        if (!serviceLogs[service.id]) serviceLogs[service.id] = [];
        if (!serviceIncidents[service.id]) serviceIncidents[service.id] = [];

        const row = document.createElement('tr');
        row.dataset.id = service.id;
        // Добавляем data-testid для тестов
        row.setAttribute('data-testid', `service-row-${service.id}`);

        const nameCell = document.createElement('td');
        nameCell.textContent = service.name;
        // Добавляем бейдж аптайма
        const uptimeBadge = document.createElement('span');
        uptimeBadge.className = 'uptime-badge';
        uptimeBadge.textContent = (service.uptime !== undefined && service.uptime !== null) ? `${service.uptime}%` : '—';
        uptimeBadge.style.marginLeft = '8px';
        uptimeBadge.style.fontSize = '0.8em';
        uptimeBadge.style.padding = '2px 6px';
        uptimeBadge.style.borderRadius = '4px';
        uptimeBadge.style.backgroundColor = 'rgba(255, 255, 255, 0.1)';
        nameCell.appendChild(uptimeBadge);
        row.appendChild(nameCell);

        const urlCell = document.createElement('td');
        const link = document.createElement('a');
        link.href = service.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer'; // Безопасность
        link.textContent = service.url;
        urlCell.appendChild(link);
        row.appendChild(urlCell);

        const statusCell = document.createElement('td');
        statusCell.id = `status-${service.id}`;
        statusCell.innerHTML = '<span class="spinner"></span>';
        row.appendChild(statusCell);

        const lastCheckCell = document.createElement('td');
        lastCheckCell.id = `lastcheck-${service.id}`;
        lastCheckCell.textContent = '—';
        // TODO: Добавить title с ISO датой
        row.appendChild(lastCheckCell);

        // ячейка действий
        const actionsCell = document.createElement('td');
        actionsCell.className = 'action-buttons';

        const recheckBtn = document.createElement('button');
        recheckBtn.className = 'recheck-btn';
        recheckBtn.textContent = 'Проверить';
        recheckBtn.setAttribute('data-testid', `recheck-btn-${service.id}`); // Для тестов
        recheckBtn.onclick = () => recheckService(service.id, recheckBtn);
        actionsCell.appendChild(recheckBtn);

        const editBtn = document.createElement('button');
        editBtn.className = 'edit-btn';
        editBtn.textContent = 'Ред.';
        editBtn.setAttribute('data-testid', `edit-btn-${service.id}`); // Для тестов
        editBtn.onclick = () => openEditModal(service);
        actionsCell.appendChild(editBtn);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.textContent = 'Уд.';
        deleteBtn.setAttribute('data-testid', `delete-btn-${service.id}`); // Для тестов
        deleteBtn.onclick = () => deleteService(service.id, service.name);
        actionsCell.appendChild(deleteBtn);

        // Новая кнопка Логи
        const logsBtn = document.createElement('button');
        logsBtn.className = 'edit-btn';
        logsBtn.textContent = 'Логи';
        logsBtn.setAttribute('data-testid', `logs-btn-${service.id}`);
        logsBtn.onclick = () => openLogsModal(service);
        actionsCell.appendChild(logsBtn);

        row.appendChild(actionsCell);

        // новый блок для сворачиваемого графика и инцидентов
        const chartRow = document.createElement('tr');
        const chartCell = document.createElement('td');
        chartCell.colSpan = 5;
        // Создаем контейнер для сворачиваемого графика с улучшенным дизайном
        chartCell.innerHTML = `
            <div class="service-chart-container">
                <div class="service-chart-header" onclick="event.stopPropagation(); toggleChart(${service.id})">
                    <h3>${service.name} - Аптайм: <span id="uptime-${service.id}">—</span></h3>
                    <button class="service-chart-toggle" id="toggle-btn-${service.id}" onclick="event.stopPropagation(); toggleChart(${service.id})">−</button>
                </div>
                <div class="service-chart-content ${visibleCharts.has(service.id) ? '' : 'collapsed'}" id="chart-content-${service.id}">
                    <div class="chart-container">
                        <div class="chart-grid"></div>
                        <canvas id="chart-${service.id}"></canvas>
                    </div>
                    <div class="chart-legend">
                        <div class="legend-item">
                            <div class="legend-color legend-up"></div>
                            <span>UP</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color legend-down"></div>
                            <span>DOWN</span>
                        </div>
                        <div class="legend-item">
                            <div class="legend-color legend-unknown"></div>
                            <span>UNKNOWN</span>
                        </div>
                    </div>
                    <div class="incident-log" id="incidents-${service.id}">
                        <p>Загрузка инцидентов...</p>
                    </div>
                </div>
            </div>`;
        chartRow.appendChild(chartCell);
        servicesList.appendChild(row);
        servicesList.appendChild(chartRow);

        // Инициализируем график после добавления в DOM, если он должен быть виден
        // Используем setTimeout(0) для гарантии, что DOM элементы уже созданы
        setTimeout(() => {
            if (visibleCharts.has(service.id) || !document.getElementById(`chart-content-${service.id}`).classList.contains('collapsed')) {
                 // Проверяем, создан ли уже график для этого сервиса
                 if (!service.chart) {
                     service.chart = createChart(service.id);
                 }
                 // Загружаем данные для графика и инцидентов
                 if (service.chart) {
                     fetchStatus(service.id);
                 }
            }
        }, 0);
    });

    // Обновляем индикаторы сортировки
    document.querySelectorAll('.sortable').forEach(header => {
        const sortField = header.dataset.sort;
        const indicator = header.querySelector('.sort-indicator');
        if (sortField === currentSortBy) {
            indicator.textContent = currentSortDirection === 'asc' ? '↑' : '↓';
        } else {
            indicator.textContent = '';
        }
    });
}


// --- Загрузка списка сервисов ---
async function fetchServices() {
    try {
        services = await apiCall('/services');
        renderServices(); // Применит фильтры и сортировку
    } catch (err) {
        console.error("Ошибка при загрузке сервисов:", err);
        notificationManager.show(`Ошибка сети: ${err.message}`);
    }
}

// --- Получение статуса и данных сервиса ---
async function fetchStatus(id) {
    const statusCell = document.getElementById(`status-${id}`);
    const lastCheckCell = document.getElementById(`lastcheck-${id}`);
    const uptimeCell = document.getElementById(`uptime-${id}`);
    if (!statusCell || !lastCheckCell) return;
    try {
        const data = await apiCall(`/status/${id}`);
        const currentStatus = data.ok;
        const previousStatus = notificationManager.previousStatuses[id];
        const serviceObj = services.find(s => s.id == id);

        // Очищаем статус и добавляем новый
        statusCell.innerHTML = '';
        statusCell.appendChild(getStatusElement(currentStatus));
        lastCheckCell.textContent = formatDate(data.ts);
        // TODO: Добавить title с ISO датой к lastCheckCell

        // Обновляем логи и график
        if (!serviceLogs[id]) serviceLogs[id] = [];
        serviceLogs[id].push({
            timestamp: formatDate(data.ts),
            status: currentStatus === true ? 1 : 0
        });
        if (serviceLogs[id].length > 20) {
            serviceLogs[id].shift();
        }

        // Обновляем график, если он инициализирован
        if (serviceObj && serviceObj.chart) {
            serviceObj.chart.data.labels = serviceLogs[id].map(l => l.timestamp);
            serviceObj.chart.data.datasets[0].data = serviceLogs[id].map(l => l.status);
            serviceObj.chart.update();
        }

        // Аптайм
        if (uptimeCell) {
            uptimeCell.textContent = (data.uptime !== undefined && data.uptime !== null) ? data.uptime + '%' : '—';
        }

        // Обновляем инциденты
        if (!serviceIncidents[id]) serviceIncidents[id] = [];
        if (data.incidents) {
            serviceIncidents[id] = data.incidents;
        }
        renderIncidents(id, serviceIncidents[id]);

        // Уведомления об инцидентах
        if (previousStatus === undefined) {
            notificationManager.setInitialStatus(id, currentStatus);
        } else {
            notificationManager.handleIncidentNotification(id, serviceObj?.name || `ID:${id}`, currentStatus, previousStatus);
        }
    } catch(err) {
        console.error(`Ошибка при проверке сервиса ${id}:`, err);
        statusCell.innerHTML = '';
        statusCell.appendChild(getStatusElement(null));
        lastCheckCell.textContent = '—';
        if (uptimeCell) {
            uptimeCell.textContent = '—';
        }
        renderIncidents(id, serviceIncidents[id] || []);
        // Уведомления об инцидентах при ошибке
        const previousStatus = notificationManager.previousStatuses[id];
        const serviceObj = services.find(s => s.id == id);
        if (previousStatus === undefined) {
            notificationManager.setInitialStatus(id, null);
        } else if (previousStatus !== null) {
            notificationManager.handleIncidentNotification(
                id,
                serviceObj?.name || `ID:${id}`,
                null,
                previousStatus
            );
        }
    }
}

// --- Добавление сервиса ---
async function addService(data) {
    try {
        const newService = await apiCall('/services', {
            method: 'POST',
            headers: { 'Content-Type':'application/json' },
            body: JSON.stringify({
                name: data.name,
                url: data.url,
                interval_s: data.interval,
                timeout_s: data.timeout
            })
        });
        notificationManager.show('Сервис добавлен!', false);
        if (serviceForm) serviceForm.reset();
        // Добавляем новый сервис в локальный список
        services.push(newService);
        // Обновляем UI
        renderServices();
    } catch(err) {
        notificationManager.show(`Ошибка: ${err.message}`);
    }
}

// --- Ручная проверка сервиса ---
async function recheckService(id, button) {
    const statusCell = document.getElementById(`status-${id}`);
    if (!statusCell || !button) return;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = '...'; // Или спиннер
    statusCell.innerHTML = '<span class="spinner"></span>';
    try {
        await apiCall(`/services/${id}/recheck`, {
            method: 'POST'
        });
        // Небольшая задержка для имитации проверки
        await new Promise(r => setTimeout(r, 1000));
        await fetchStatus(id); // Обновляем статус после проверки
    } catch(err) {
        notificationManager.show(`Ошибка проверки: ${err.message}`);
        statusCell.innerHTML = '';
        statusCell.appendChild(getStatusElement(null));
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}

// --- Редактирование сервиса ---
async function updateService(id, data) {
     try {
        const updatedService = await apiCall(`/services/${id}`, {
            method: 'PUT',
            headers: { 'Content-Type':'application/json' },
            body: JSON.stringify({
                name: data.name,
                url: data.url,
                interval_s: data.interval,
                timeout_s: data.timeout
            })
        });
        notificationManager.show('Сервис обновлён!', false);
        // Обновляем сервис в локальном списке
        const index = services.findIndex(s => s.id === id);
        if (index !== -1) {
            services[index] = updatedService;
        }
        // Обновляем UI
        renderServices();
        closeEditModal();
    } catch(err) {
        notificationManager.show(`Ошибка обновления: ${err.message}`);
    }
}

// --- Удаление сервиса ---
async function deleteService(id, name) {
    if (!confirm(`Вы уверены, что хотите удалить сервис "${name}"?`)) {
        return;
    }
    try {
        await apiCall(`/services/${id}`, {
            method: 'DELETE'
        });
        notificationManager.show('Сервис удалён!', false);
    } catch(err) {
        // Даже если сервер вернул 204 без тела и парсинг не потребовался,
        // а также на случай сетевых ошибок — показываем сообщение, но всё равно синхронизируем UI ниже
        // Если сервер удалил без тела, это не ошибка
        notificationManager.show('Сервис удалён!', false);
    } finally {
        // Удаляем сервис из локального списка
        services = services.filter(s => s.id !== id);
        // Удаляем связанные данные
        delete serviceLogs[id];
        delete serviceIncidents[id];
        // Удаляем из набора видимых графиков
        visibleCharts.delete(id);
        // Обновляем UI
        renderServices();
    }
}

// --- Модальное окно редактирования ---
let currentEditService = null;
const editModal = document.getElementById('editModal');
const editForm = document.getElementById('editServiceForm');

// Логи: состояние и элементы
let currentLogsService = null;
const logsModal = document.getElementById('logsModal');
const logsBody = document.getElementById('logsBody');
const logsTitle = document.getElementById('logsTitle');

function openEditModal(service) {
    currentEditService = service;
    if (!editModal || !editForm) return;

    document.getElementById('editName').value = service.name;
    document.getElementById('editUrl').value = service.url;
    document.getElementById('editInterval').value = service.interval_s;
    document.getElementById('editTimeout').value = service.timeout_s;

    editModal.style.display = 'block';
}

function closeEditModal() {
    if (editModal) {
        editModal.style.display = 'none';
    }
    currentEditService = null;
}

function openLogsModal(service) {
    currentLogsService = service;
    if (!logsModal || !logsBody) return;
    logsTitle.textContent = `Логи: ${service.name}`;
    logsBody.innerHTML = '<div class="spinner" style="margin: 12px auto;"></div>';
    logsModal.style.display = 'block';
    // Подгружаем историю
    renderLogs(service.id);
}

function closeLogsModal() {
    if (logsModal) {
        logsModal.style.display = 'none';
    }
    currentLogsService = null;
}

function deriveErrorType(item) {
    if (item.ok === true) return '—';
    if (item.error) {
        const e = item.error.toLowerCase();
        if (e.includes('timeout')) return 'Timeout';
        if (e.includes('ssl')) return 'SSL';
        if (e.includes('connect')) return 'Connect';
        if (e.includes('dns')) return 'DNS';
        return 'Client';
    }
    if (item.status_code) {
        if (item.status_code >= 500) return 'HTTP 5xx';
        if (item.status_code >= 400) return 'HTTP 4xx';
    }
    return 'Unknown';
}

async function renderLogs(serviceId) {
    try {
        const data = await apiCall(`/services/${serviceId}/history?limit=100`);
        // Сформируем таблицу
        let html = '';
        if (!data || data.length === 0) {
            html = '<p>История пуста.</p>';
        } else {
            html = `
            <div class="card" style="margin: 0;">
                <table>
                    <thead>
                        <tr>
                            <th>Время</th>
                            <th>Статус</th>
                            <th>Код</th>
                            <th>Отклик (мс)</th>
                            <th>Тип ошибки</th>
                            <th>Текст ошибки</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${data.map(item => {
                            const statusText = item.ok ? 'UP' : 'DOWN';
                            const code = item.status_code ?? '—';
                            const lat = (item.latency_ms ?? '—');
                            const errType = deriveErrorType(item);
                            const errText = item.error ? item.error : '—';
                            const ts = item.ts ? new Date(item.ts).toLocaleString() : '—';
                            return `<tr>
                                <td style="width: 18%">${ts}</td>
                                <td style="width: 8%">${statusText}</td>
                                <td style="width: 8%">${code}</td>
                                <td style="width: 10%">${lat}</td>
                                <td style="width: 12%">${errType}</td>
                                <td class="error-text" style="width: 44%">${errText}</td>
                            </tr>`;
                        }).join('')}
                    </tbody>
                </table>
            </div>`;
        }
        logsBody.innerHTML = html;
    } catch (err) {
        logsBody.innerHTML = `<p style="color:#f44336;">Ошибка загрузки логов: ${err.message}</p>`;
    }
}

// --- Инициализация ---
document.addEventListener('DOMContentLoaded', () => {
    fetchServices();

    // --- Обработчики формы добавления ---
    if (serviceForm) {
        serviceForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const name = document.getElementById('name')?.value.trim();
            const url = document.getElementById('url')?.value.trim();
            const interval = parseInt(document.getElementById('interval')?.value);
            const timeout = parseInt(document.getElementById('timeout')?.value);
            if(!url) {
                notificationManager.show('URL обязателен');
                return;
            }
            if(interval < 60) {
                notificationManager.show('Интервал должен быть не менее 60 секунд');
                return;
            }
            if(timeout < 1) {
                notificationManager.show('Таймаут должен быть не менее 1 секунды');
                return;
            }
            const addButton = document.getElementById('addButton');
            if (addButton) addButton.disabled = true;
            await addService({name, url, interval, timeout});
            if (addButton) addButton.disabled = false;
        });
    }

    // --- Обработчик кнопки обновления списка ---
    if (refreshButton) {
        refreshButton.addEventListener('click', () => {
            refreshButton.disabled = true;
            fetchServices().finally(() => {
                refreshButton.disabled = false;
            });
        });
    }

    // --- Обработчики фильтрации и поиска ---
    if (statusFilter) {
        statusFilter.addEventListener('change', (e) => {
            currentFilter = e.target.value;
            renderServices();
        });
    }
    if (searchInput) {
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                currentSearchTerm = e.target.value.trim();
                renderServices();
            }, 300); // Debounce
        });
    }

    // --- Обработчики сортировки ---
    document.querySelectorAll('.sortable').forEach(header => {
        header.addEventListener('click', () => {
            const sortBy = header.dataset.sort;
            if (currentSortBy === sortBy) {
                currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
            } else {
                currentSortBy = sortBy;
                currentSortDirection = 'asc';
            }
            renderServices();
        });
    });

    // --- Интервал обновления статусов (с умным backoff и паузой) ---
    let pollInterval = 30000; // 30 сек
    let pollTimerId;
    const maxPollInterval = 120000; // 2 мин

    const schedulePoll = () => {
        pollTimerId = setTimeout(async () => {
            try {
                // Обновляем статусы всех отображаемых сервисов
                const filteredServices = applyFiltersAndSort();
                await Promise.all(filteredServices.map(s => fetchStatus(s.id)));
                pollInterval = 30000; // Сброс при успехе
            } catch (err) {
                console.warn("Ошибка при фоновом обновлении статусов:", err);
                pollInterval = Math.min(pollInterval * 2, maxPollInterval); // Увеличение интервала при ошибке
            } finally {
                if (!document.hidden) { // Проверяем видимость вкладки
                    schedulePoll();
                }
            }
        }, pollInterval);
    };

    // Запуск поллинга
    schedulePoll();

    // Пауза при неактивной вкладке
    document.addEventListener("visibilitychange", () => {
        if (document.hidden) {
            clearTimeout(pollTimerId);
            console.log("Поллинг приостановлен: вкладка неактивна");
        } else {
            console.log("Поллинг возобновлён: вкладка активна");
            schedulePoll(); // Перезапуск
        }
    });

    // --- Обработчики модального окна редактирования ---
    if (editForm) {
        editForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!currentEditService) return;

            const name = document.getElementById('editName')?.value.trim();
            const url = document.getElementById('editUrl')?.value.trim();
            const interval = parseInt(document.getElementById('editInterval')?.value);
            const timeout = parseInt(document.getElementById('editTimeout')?.value);

             if(!url) {
                notificationManager.show('URL обязателен');
                return;
            }
            if(interval < 60) {
                notificationManager.show('Интервал должен быть не менее 60 секунд');
                return;
            }
            if(timeout < 1) {
                notificationManager.show('Таймаут должен быть не менее 1 секунды');
                return;
            }

            const updateButton = document.querySelector('#editModal button[type="submit"]');
            if (updateButton) updateButton.disabled = true;
            await updateService(currentEditService.id, {name, url, interval, timeout});
            if (updateButton) updateButton.disabled = false;
        });
    }

    const closeModalBtn = document.querySelector('.close-modal');
    if (closeModalBtn) {
        closeModalBtn.addEventListener('click', closeEditModal);
    }

    // Кнопка закрытия логов
    const closeLogsBtn = document.getElementById('closeLogsBtn');
    if (closeLogsBtn) {
        closeLogsBtn.addEventListener('click', closeLogsModal);
    }

    window.addEventListener('click', (event) => {
        if (event.target === editModal) {
            closeEditModal();
        }
        if (event.target === logsModal) {
            closeLogsModal();
        }
    });
});
