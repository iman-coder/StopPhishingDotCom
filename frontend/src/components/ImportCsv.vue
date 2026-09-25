<!-- ImportCsv.vue -->
<template>
  <div class="my-4 p-3 border rounded bg-light">
    <h5>Import CSV</h5>

    <input 
      type="file" 
      accept=".csv" 
      @change="onFileChange" 
      class="form-control"
      :disabled="isUploading"
    />

    <button 
      class="btn btn-primary mt-2"
      :disabled="!csvFile || isUploading"
      @click="uploadCsv"
    >
      <span v-if="isUploading">
        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
        Uploading...
      </span>
      <span v-else>Upload CSV</span>
    </button>

    <!-- Progress Bar for Large Files -->
    <div v-if="isUploading && showProgress" class="mt-3">
      <div class="d-flex justify-content-between mb-1">
        <small class="text-muted">Upload Progress</small>
        <small class="text-muted">{{ uploadProgress }}%</small>
      </div>
      <div class="progress" style="height: 25px;">
        <div 
          class="progress-bar progress-bar-striped progress-bar-animated" 
          role="progressbar"
          :style="{ width: uploadProgress + '%' }"
          :aria-valuenow="uploadProgress"
          aria-valuemin="0"
          aria-valuemax="100"
        >
          {{ uploadProgress }}%
        </div>
      </div>
      <div v-if="processing" class="mt-2">
        <div class="d-flex align-items-center">
          <div class="spinner-border spinner-border-sm text-primary me-2" role="status">
            <span class="visually-hidden">Processing...</span>
          </div>
          <small class="text-muted">Processing file... This may take a while for large files.</small>
        </div>
      </div>
    </div>

    <!-- Success/Error Messages -->
    <div v-if="message" class="mt-2">
      <div v-if="messageType === 'success'" class="alert alert-success alert-dismissible fade show" role="alert">
        <strong>Success!</strong> {{ message }}
        <button type="button" class="btn-close" @click="message = ''" aria-label="Close"></button>
      </div>
      <div v-else-if="messageType === 'error'" class="alert alert-danger alert-dismissible fade show" role="alert">
        <strong>Error!</strong> {{ message }}
        <button type="button" class="btn-close" @click="message = ''" aria-label="Close"></button>
      </div>
      <div v-else class="text-info">{{ message }}</div>
    </div>
  </div>
</template>

<script>
import { importCSV } from "../services/csvService";

export default {
  name: "ImportCsv",
  data() {
    return {
      csvFile: null,
      message: "",
      messageType: "", // 'success', 'error', or ''
      isUploading: false,
      uploadProgress: 0,
      processing: false,
      showProgress: false,
    };
  },
  methods: {
    onFileChange(e) {
      this.csvFile = e.target.files[0];
      this.message = "";
      this.messageType = "";
      this.uploadProgress = 0;
      this.showProgress = false;
      
      // Show progress bar for files larger than 1MB
      if (this.csvFile && this.csvFile.size > 1024 * 1024) {
        this.showProgress = true;
      }
    },

    async uploadCsv() {
      if (!this.csvFile) return;

      this.isUploading = true;
      this.uploadProgress = 0;
      this.processing = false;
      this.message = "";
      this.messageType = "";

      try {
        const result = await importCSV(this.csvFile, (progress) => {
          if (progress.type === 'upload') {
            this.uploadProgress = progress.percent;
            
            // When upload is complete, show processing indicator
            if (progress.percent >= 100) {
              this.processing = true;
            }
          }
        });

        // Upload complete, processing result
        this.processing = false;
        this.isUploading = false;
        
        // Format success message with import stats
        if (result.inserted !== undefined) {
          const inserted = result.inserted || 0;
          const skipped = result.skipped || 0;
          const chunks = result.chunks_processed || 0;
          const sizeMB = result.total_size_bytes 
            ? (result.total_size_bytes / (1024 * 1024)).toFixed(2) 
            : null;
          
          let successMsg = `Successfully imported ${inserted} URL${inserted !== 1 ? 's' : ''}`;
          if (skipped > 0) {
            successMsg += `, skipped ${skipped} duplicate${skipped !== 1 ? 's' : ''}`;
          }
          if (chunks > 0) {
            successMsg += ` (processed in ${chunks} chunk${chunks !== 1 ? 's' : ''}`;
            if (sizeMB) {
              successMsg += `, ${sizeMB} MB`;
            }
            successMsg += `)`;
          }
          
          this.message = successMsg;
          this.messageType = 'success';
        } else {
          this.message = result.message || "Import successful!";
          this.messageType = 'success';
        }
        
        this.$emit("refresh");
        
        // Reset file input after successful import
        this.csvFile = null;
        this.showProgress = false;
        this.uploadProgress = 0;
      } catch (err) {
        console.error("CSV import failed:", err);
        this.isUploading = false;
        this.processing = false;
        
        // Extract error message
        let errorMsg = "Import failed.";
        if (err.response && err.response.data) {
          if (typeof err.response.data === 'string') {
            errorMsg = err.response.data;
          } else if (err.response.data.detail) {
            errorMsg = err.response.data.detail;
          } else if (err.response.data.message) {
            errorMsg = err.response.data.message;
          }
        } else if (err.message) {
          errorMsg = err.message;
        }
        
        this.message = errorMsg;
        this.messageType = 'error';
      }
    }
  }
};
</script>

<style scoped>
.progress {
  border-radius: 0.375rem;
}

.progress-bar {
  font-size: 0.875rem;
  font-weight: 500;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
