// src/services/csvService.js
import axios from "axios";
import { attachAuthHeader } from "./authService";

// Ensure Authorization header is attached if token present
attachAuthHeader();

// Use API prefix so CSV endpoints are proxied to backend
const API = "/api/urls";

export async function exportCSV() {
    const response = await axios.get(`${API}/export`, {
        responseType: "blob" // important for downloading files
    });
    return response.data;
}

export async function importCSV(file, onProgress) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await axios.post(`${API}/import`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
                const percentCompleted = Math.round(
                    (progressEvent.loaded * 100) / progressEvent.total
                );
                onProgress({
                    type: 'upload',
                    percent: percentCompleted,
                    loaded: progressEvent.loaded,
                    total: progressEvent.total
                });
            }
        }
    });
    return response.data;
}
