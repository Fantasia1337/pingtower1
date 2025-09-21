// static/js/api.js
/**
 * @fileoverview Единый модуль для работы с API.
 * Обеспечивает таймауты, повторные попытки и нормализацию ошибок.
 */

const API_BASE = '';
const DEFAULT_TIMEOUT = 10000; // 10 секунд

/**
 * @typedef {Object} ApiError
 * @property {string} message - Сообщение об ошибке.
 * @property {number} status - HTTP статус.
 */

/**
 * Выполняет HTTP-запрос к API.
 * @param {string} url - Путь к эндпоинту (относительно API_BASE).
 * @param {RequestInit} [options={}] - Опции fetch.
 * @returns {Promise<any>} - Promise с данными ответа.
 * @throws {ApiError} - Если запрос завершился ошибкой.
 */
export async function apiCall(url, options = {}) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT);

    try {
        const response = await fetch(API_BASE + url, {
            ...options,
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (response.status === 204) {
            return null;
        }
        if (!response.ok) {
            // Попытаться распарсить JSON ошибки
            let errorData;
            try {
                errorData = await response.json();
            } catch (e) {
                errorData = { message: response.statusText };
            }
            const error = new Error(errorData.message || 'Ошибка запроса');
            error.status = response.status;
            throw error;
        }

        // Если ответ пустой (например, 204 No Content), возвращаем null
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            try {
                return await response.json();
            } catch (e) {
                return null;
            }
        } else {
            return null; // или response.text() если ожидается текст
        }
    } catch (error) {
        clearTimeout(timeoutId);
        if (error.name === 'AbortError') {
            const timeoutError = new Error('Таймаут запроса');
            timeoutError.status = 0; // Кастомный код для таймаута
            throw timeoutError;
        }
        // Для сетевых ошибок и других исключений
        if (!error.status) {
            error.status = -1; // Кастомный код для сетевых ошибок
        }
        throw error;
    }
}

/**
 * @typedef {Object} ServiceDTO
 * @property {string} id
 * @property {string} name
 * @property {string} url
 * @property {number} interval
 * @property {number} timeout
 * @property {string} created_at
 * @property {string} status
 * @property {string|null} lastChecked
 * @property {number} uptime
 * @property {Array} history
 * @property {Array<string>} incidents
 */

/**
 * @typedef {Object} StatusDTO
 * @property {boolean} ok
 * @property {string|null} lastCheck
 * @property {number} uptime
 * @property {Array} incidents
 */

/**
 * @typedef {Object} IncidentDTO
 * @property {string} id
 * @property {string} service_id
 * @property {string} service_name
 * @property {string} start
 * @property {string|null} end
 * @property {string} error_message
 */

/**
 * @typedef {Object} HistoryEntryDTO
 * @property {string} timestamp
 * @property {boolean} status
 * @property {number|null} response_time
 * @property {string|null} error
 */
