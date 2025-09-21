// static/js/notifications.js
/**
 * @fileoverview Менеджер уведомлений для PingTower.
 */

export class NotificationManager {
    constructor() {
        this.notificationEl = document.getElementById('notification');
        this.previousStatuses = {}; // Храним предыдущие статусы сервисов для определения изменений
    }

    /**
     * Показывает уведомление.
     * @param {string} message - Текст сообщения.
     * @param {boolean} [isError=true] - Является ли сообщение ошибкой.
     */
    show(message, isError = true) {
        if (!this.notificationEl) return;
        this.notificationEl.textContent = message;
        this.notificationEl.classList.remove('hidden');
        this.notificationEl.style.backgroundColor = isError ? '#dc3545' : '#28a745';
        setTimeout(() => this.hide(), 5000);
    }

    /** Скрывает уведомление. */
    hide() {
        if (this.notificationEl) {
            this.notificationEl.classList.add('hidden');
        }
    }

    /**
     * Обрабатывает уведомления об инцидентах на основе изменения статуса.
     * @param {string} serviceId - ID сервиса.
     * @param {string} serviceName - Имя сервиса.
     * @param {boolean|null} currentStatus - Текущий статус (true - up, false - down, null - unknown/error).
     * @param {boolean|null} previousStatus - Предыдущий статус.
     */
    handleIncidentNotification(serviceId, serviceName, currentStatus, previousStatus) {
        // Проверяем переходы статусов
        if (previousStatus === true && currentStatus === false) {
            // Сервис упал - новый инцидент
            this.show(`⚠️ Инцидент: Сервис "${serviceName}" стал недоступен!`, true);
        } else if (previousStatus === false && currentStatus === true) {
            // Сервис восстановился
            this.show(`✅ Восстановление: Сервис "${serviceName}" снова доступен.`, false);
        }
        // Обновляем предыдущий статус
        this.previousStatuses[serviceId] = currentStatus;
    }

    /**
     * Устанавливает начальный статус сервиса, чтобы избежать ложных уведомлений.
     * @param {string} serviceId - ID сервиса.
     * @param {boolean|null} status - Начальный статус.
     */
    setInitialStatus(serviceId, status) {
        this.previousStatuses[serviceId] = status;
    }
}

// Экспортируем экземпляр для использования в других модулях
export const notificationManager = new NotificationManager();
