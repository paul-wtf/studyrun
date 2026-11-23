{{/*
Chart name, truncated to 63 chars (k8s label limit).
*/}}
{{- define "studyrun.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Fully qualified app name. Uses fullnameOverride if set, otherwise
<release>-<chart> (or just <release> if release == chart name).
*/}}
{{- define "studyrun.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "studyrun.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{ include "studyrun.selectorLabels" . }}
{{- end }}

{{/*
Selector labels (shared between all components).
*/}}
{{- define "studyrun.selectorLabels" -}}
app.kubernetes.io/name: {{ include "studyrun.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Backend selector labels.
*/}}
{{- define "studyrun.backendSelectorLabels" -}}
{{ include "studyrun.selectorLabels" . }}
app.kubernetes.io/component: backend
{{- end }}

{{/*
Frontend selector labels.
*/}}
{{- define "studyrun.frontendSelectorLabels" -}}
{{ include "studyrun.selectorLabels" . }}
app.kubernetes.io/component: frontend
{{- end }}

{{/*
Name of the Secret to use. Returns existingSecret if set, otherwise
the generated name.
*/}}
{{- define "studyrun.secretName" -}}
{{- if .Values.secrets.existingSecret }}
{{- .Values.secrets.existingSecret }}
{{- else }}
{{- include "studyrun.fullname" . }}
{{- end }}
{{- end }}
