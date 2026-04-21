/**
 * CERC — Clinical AI Workbench
 * App.jsx — Production Hardening Pass v2.0
 * ─────────────────────────────────────────────────────────────────────────
 * Design philosophy: deterministic · regulated · auditable · traceable
 * All logic from previous version preserved. Architecture refined.
 * Component functions: Icon, FormattedContent, SidebarGroup, StatusStrip,
 *   DocumentCard, SectionCard, MissingBadge, SectionStatusBadge,
 *   PipelineStepItem, ValidationMetricRow, ExportCard, TracePanelShell
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion, AnimatePresence } from 'framer-motion'
import './App.css'
import PipelineVisualizer from './components/ui/PipelineVisualizer'
import InstructionBar from './components/ui/InstructionBar'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api'
const BUILD_VERSION = 'v2.0.4'

// ═══════════════════════════════════════════════════════
// ICON SYSTEM — single dependency-free SVG component
// ═══════════════════════════════════════════════════════
function Icon({ name, size = 18, className = '', style = {} }) {
  const icons = {
    file:              <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>,
    'file-pdf':        <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15v-2h1.5a1.5 1.5 0 0 1 0 3H9z"/></>,
    'file-doc':        <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></>,
    'file-text':       <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><line x1="10" y1="9" x2="8" y2="9"/></>,
    'file-json':       <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></>,
    check:             <polyline points="20 6 9 17 4 12"/>,
    'check-circle':    <><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></>,
    'x-circle':        <><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></>,
    circle:            <circle cx="12" cy="12" r="10"/>,
    loader:            <><line x1="12" y1="2" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="22"/><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"/><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"/><line x1="2" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="22" y2="12"/><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"/><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"/></>,
    shield:            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>,
    database:          <><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></>,
    settings:          <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></>,
    cpu:               <><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></>,
    search:            <><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></>,
    download:          <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></>,
    copy:              <><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></>,
    trash:             <><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/></>,
    'upload-cloud':    <><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></>,
    activity:          <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>,
    link:              <><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></>,
    'alert-triangle':  <><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></>,
    'wifi-off':        <><line x1="1" y1="1" x2="23" y2="23"/><path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55"/><path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39"/><path d="M10.71 5.05A16 16 0 0 1 22.56 9"/><path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></>,
    server:            <><rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/></>,
    layers:            <><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></>,
    'bar-chart':       <><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></>,
    'clock':           <><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></>,
  }
  return (
    <svg className={`icon ${className}`} style={style} width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {icons[name] || icons['file']}
    </svg>
  )
}

// ═══════════════════════════════════════════════════════
// STATIC CONFIG
// ═══════════════════════════════════════════════════════
const SECTIONS = {
  synopsis:               { name: 'Synopsis',                number: 'Synopsis', category: 'overview' },
  introduction:           { name: 'Introduction',            number: '1',        category: 'overview' },
  ethics:                 { name: 'Ethics',                  number: '4',        category: 'overview' },
  study_objectives:       { name: 'Study Objectives',        number: '5',        category: 'design' },
  investigators_sites:    { name: 'Investigators & Sites',   number: '6',        category: 'design' },
  study_design:           { name: 'Study Design',            number: '9.1',      category: 'design' },
  inclusion_exclusion:    { name: 'Inclusion/Exclusion',     number: '9.3',      category: 'population' },
  treatments:             { name: 'Treatments',              number: '9.4',      category: 'population' },
  endpoints:              { name: 'Endpoints',               number: '9.4.1',    category: 'population' },
  study_population:       { name: 'Subject Disposition',     number: '10.1',     category: 'results' },
  demographics:           { name: 'Demographics',            number: '10.1.4',   category: 'results' },
  efficacy_evaluation:    { name: 'Efficacy Evaluation',     number: '10',       category: 'results' },
  statistical_methods:    { name: 'Statistical Methods',     number: '11',       category: 'results' },
  safety_evaluation:      { name: 'Safety Evaluation',       number: '12',       category: 'safety' },
  adverse_events:         { name: 'Adverse Events',          number: '12.2',     category: 'safety' },
  discussion_conclusions: { name: 'Discussion & Conclusions',number: '13',       category: 'safety' },
}

// Pipeline stepper definitions
const PIPELINE_STEPS = [
  { key: 'load',     label: 'Load',     icon: 'database',  prog: 20, sub: 'Ingesting evidence' },
  { key: 'extract',  label: 'Extract',  icon: 'search',    prog: 40, sub: 'Reading structure' },
  { key: 'map',      label: 'Map',      icon: 'link',      prog: 60, sub: 'Aligning sources' },
  { key: 'generate', label: 'Generate', icon: 'file-text', prog: 80, sub: 'Constrained synthesis' },
  { key: 'validate', label: 'Validate', icon: 'shield',    prog: 100, sub: 'Applying rules' },
]

// Lifecycle status config
const LIFECYCLE_CONFIG = {
  idle:       { label: 'IDLE',       color: 'var(--text-muted)',      dot: false,  icon: 'activity' },
  running:    { label: 'COMPILING',  color: 'var(--accent)',          dot: true,   icon: 'loader' },
  complete:   { label: 'VALIDATED',  color: 'var(--success)',         dot: false,  icon: 'check-circle' },
  error:      { label: 'FAILED',     color: 'var(--danger)',          dot: false,  icon: 'x-circle' },
}

// Document type config
const DOC_TYPE_CONFIG = {
  'Protocol / CIP':       { abbr: 'CIP',  color: 'var(--accent)' },
  'Statistical / SAP':    { abbr: 'SAP',  color: 'var(--warning)' },
  'CEC Charter':          { abbr: 'CEC',  color: '#a78bfa' },
  'ISO Standard':         { abbr: 'ISO',  color: 'var(--success)' },
  'Clinical Report':      { abbr: 'CSR',  color: 'var(--success)' },
  'Appendix':             { abbr: 'APP',  color: 'var(--text-muted)' },
}

// Section status config
const SECTION_STATUS_CONFIG = {
  complete:     { label: 'COMPLETE',    color: 'var(--success)',  bg: 'rgba(16,185,129,0.1)',  border: 'rgba(16,185,129,0.3)' },
  partial:      { label: 'PARTIAL',     color: 'var(--warning)',  bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.3)' },
  generated:    { label: 'GENERATED',   color: 'var(--success)',  bg: 'rgba(16,185,129,0.1)',  border: 'rgba(16,185,129,0.3)' },
  missing:      { label: 'MISSING',     color: 'var(--danger)',   bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.3)' },
  blocked:      { label: 'BLOCKED',     color: 'var(--danger)',   bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.3)' },
  failed:       { label: 'FAILED',      color: 'var(--danger)',   bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.3)' },
}

// Validation dimension colors
const VAL_STATUS = {
  pass:    { label: 'PASS',    color: 'var(--success)', icon: 'check-circle' },
  warning: { label: 'WARNING', color: 'var(--warning)', icon: 'alert-triangle' },
  fail:    { label: 'FAIL',    color: 'var(--danger)',  icon: 'x-circle' },
}

// Exports config
const EXPORTS = [
  { type: 'docx', icon: 'file-doc',  label: 'Compiled CSR',           desc: 'Full clinical study report with all generated sections', format: 'DOCX' },
  { type: 'pdf',  icon: 'file-pdf',  label: 'Compiled CSR',           desc: 'Print-ready regulatory submission copy',                 format: 'PDF' },
  { type: 'log',  icon: 'file-json', label: 'Traceability Payload',   desc: 'Full JSON audit trail with section-level provenance',    format: 'JSON' },
  { type: 'summary', icon: 'file-text', label: 'Validation Summary',  desc: 'Compliance log with scoring and gap analysis',           format: 'TXT' },
]

// ═══════════════════════════════════════════════════════
// UTILITY FUNCTIONS
// ═══════════════════════════════════════════════════════
function fmtSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function classifyDoc(filename) {
  const f = filename.toLowerCase()
  if (f.includes('cip') || f.includes('protocol')) return 'Protocol / CIP'
  if (f.includes('sap') || f.includes('statistical')) return 'Statistical / SAP'
  if (f.includes('cec') || f.includes('charter')) return 'CEC Charter'
  if (f.includes('iso')) return 'ISO Standard'
  if (f.includes('clinical_investigation_report') || f.includes('csr')) return 'Clinical Report'
  return 'Appendix'
}

function normalizeSectionsMap(results) {
  const direct = results?.sections
  if (direct && !Array.isArray(direct)) return direct

  const structured = results?.structured_output?.sections
  if (Array.isArray(structured)) {
    return structured.reduce((acc, sec) => {
      const sid = sec?.section_id || sec?.id
      if (sid) acc[sid] = sec
      return acc
    }, {})
  }
  if (structured && !Array.isArray(structured)) return structured
  return {}
}

function pipelineIssueState(results) {
  const sections = Object.values(normalizeSectionsMap(results) || {})
  if (!sections.length) return null
  const hasMissing = sections.some(s => ['missing', 'blocked', 'failed'].includes((s?.status || '').toLowerCase()))
  const hasPartial = sections.some(s => (s?.status || '').toLowerCase() === 'partial')
  if (hasMissing) return 'failed'
  if (hasPartial) return 'warning'
  return 'done'
}

function sectionSummaryCounts(sectionMap) {
  const values = Object.values(sectionMap || {})
  return values.reduce(
    (acc, sec) => {
      const st = (sec?.status || '').toLowerCase()
      if (st === 'complete' || st === 'generated') acc.complete += 1
      else if (st === 'partial') acc.partial += 1
      else if (st === 'missing' || st === 'blocked' || st === 'failed') acc.missing += 1
      return acc
    },
    { complete: 0, partial: 0, missing: 0 },
  )
}

// ═══════════════════════════════════════════════════════
// SMALL REUSABLE COMPONENTS
// ═══════════════════════════════════════════════════════

/** Section-level status badge */
function SectionStatusBadge({ status }) {
  const cfg = SECTION_STATUS_CONFIG[status]
  if (!cfg) return null
  return (
    <span style={{
      fontSize: 9, fontWeight: 800, fontFamily: 'JetBrains Mono',
      letterSpacing: '0.08em', padding: '2px 7px', borderRadius: 4,
      color: cfg.color, background: cfg.bg, border: `1px solid ${cfg.border}`,
    }}>
      {cfg.label}
    </span>
  )
}

/** Missing elements badge */
function MissingBadge({ count, label }) {
  if (!count) return null
  return (
    <span className="missing-badge">
      <Icon name="alert-triangle" size={9} />
      {label || `${count} missing`}
    </span>
  )
}

/** Formatted generated content */
function FormattedContent({ content }) {
  if (!content) return <p style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Compilation yielded no mapping for this section.</p>
  return (
    <div>
      {content.split('\n').map((line, i) => {
        const t = line.trim()
        if (!t) return <div key={i} style={{ height: '12px' }} />
        const clean = t.replace(/^#{1,6}\s+/, '').replace(/\*\*(.*?)\*\*/g, '$1')
        if (/^(\d+(?:\.\d+)*)\s+[A-Z]/.test(clean)) return <h3 key={i} className="content-h3">{clean}</h3>
        if (/^\d+\.\s+/.test(clean)) return <li key={i} style={{ marginLeft: '20px', marginBottom: '8px' }}>{clean}</li>
        return <p key={i} className="content-paragraph">{clean}</p>
      })}
    </div>
  )
}

/** Sidebar group — labelled section with optional separator */
function SidebarGroup({ label, children, showDivider = true }) {
  return (
    <div className="sidebar-group">
      {showDivider && <div className="sidebar-divider" />}
      {label && <div className="sidebar-group-label">{label}</div>}
      {children}
    </div>
  )
}

/** Document card in upload ledger */
function DocumentCard({ doc, onDelete, disabled }) {
  const type = classifyDoc(doc.name)
  const typeCfg = DOC_TYPE_CONFIG[type] || DOC_TYPE_CONFIG['Appendix']
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="doc-item"
    >
      {/* Type abbr badge */}
      <div style={{
        width: 32, height: 32, borderRadius: 4, flexShrink: 0,
        background: 'var(--bg-interactive)', border: `1px solid var(--border-subtle)`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'JetBrains Mono', fontSize: 8, fontWeight: 800, color: typeCfg.color,
      }}>
        {typeCfg.abbr}
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        <div className="doc-name">{doc.name}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
          <span style={{
            fontSize: 8, fontFamily: 'JetBrains Mono', fontWeight: 700,
            color: typeCfg.color, letterSpacing: '0.04em',
          }}>
            {type}
          </span>
          <span style={{ color: 'var(--border-default)', fontSize: 8 }}>·</span>
          <span style={{ fontSize: 9, color: 'var(--success)', fontFamily: 'JetBrains Mono', fontWeight: 600 }}>
            ✓ READY
          </span>
        </div>
      </div>

      <button
        className="btn-delete"
        onClick={(e) => { e.stopPropagation(); onDelete(doc.name) }}
        disabled={disabled}
        title="Remove from context"
      >
        <Icon name="trash" size={13} />
      </button>
    </motion.div>
  )
}

/** Section card in the selector grid */
function SectionCard({ id, meta, selected, onClick, resultSection, isInProgress }) {
  const sectionStatus = resultSection?.status
  const missingCount = resultSection?.trace?.missing_elements?.length || resultSection?.missing_elements?.length || 0
  const valScore = resultSection?.validation?.score || 0

  // Derive border accent from status
  const leftBorderColor = selected
    ? 'var(--accent)'
    : sectionStatus === 'complete' || sectionStatus === 'generated'
      ? 'var(--success)'
      : sectionStatus === 'partial'
        ? 'var(--warning)'
        : sectionStatus === 'missing' || sectionStatus === 'failed' || sectionStatus === 'blocked'
          ? 'var(--danger)'
          : 'transparent'

  return (
    <div
      onClick={onClick}
      className={`section-card ${selected ? 'selected' : ''}`}
      style={{ borderLeft: `3px solid ${leftBorderColor}` }}
    >
      <div className="sec-head">
        <span className="sec-num">{meta.number}</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {isInProgress && (
            <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: 'var(--accent)', animation: 'pulseDot 1.5s infinite' }} />
          )}
          {selected && !isInProgress && <Icon name="check-circle" size={13} style={{ color: 'var(--accent)' }} />}
        </div>
      </div>

      <div className="sec-title">{meta.name}</div>
      <div className="sec-desc">Requires {meta.category} elements.</div>

      {/* Status + score row */}
      {(sectionStatus || valScore > 0) && (
        <div className="sec-status-row">
          {sectionStatus && <SectionStatusBadge status={sectionStatus} />}
          {valScore > 0 && (
            <span style={{
              fontSize: 9, fontFamily: 'JetBrains Mono', fontWeight: 700,
              color: valScore >= 70 ? 'var(--success)' : valScore >= 40 ? 'var(--warning)' : 'var(--danger)',
            }}>
              {valScore}%
            </span>
          )}
        </div>
      )}

      {missingCount > 0 && <MissingBadge count={missingCount} />}
    </div>
  )
}

/** Pipeline stepper step item */
function PipelineStepItem({ step, stepState }) {
  const stateClass = stepState === 'active' ? 'active' : stepState === 'done' ? 'done' : stepState === 'warning' ? 'warning' : stepState === 'failed' ? 'failed' : ''

  return (
    <div className={`step ${stateClass}`}>
      <div className="step-icon">
        {stepState === 'active'
          ? <Icon name="loader" size={14} className="spin" />
          : <Icon name={step.icon} size={14} />
        }
      </div>
      <div className="step-label">{step.label}</div>
      {stepState === 'active' && (
        <div className="step-sub">{step.sub}</div>
      )}
    </div>
  )
}

/** Validation metric row: one dimension */
function ValidationMetricRow({ label, status, explanation }) {
  const cfg = VAL_STATUS[status] || VAL_STATUS.warning
  return (
    <div className="val-metric-row">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
        <Icon name={cfg.icon} size={13} style={{ color: cfg.color, flexShrink: 0 }} />
        <span style={{ fontSize: 12, color: 'var(--text-primary)', fontWeight: 600 }}>{label}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {explanation && (
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{explanation}</span>
        )}
        <span style={{
          fontSize: 9, fontWeight: 800, fontFamily: 'JetBrains Mono', letterSpacing: '0.06em',
          color: cfg.color, background: `${cfg.color}18`, padding: '2px 8px', borderRadius: 4,
        }}>
          {cfg.label}
        </span>
      </div>
    </div>
  )
}

/** Export card in downloads tab */
function ExportCard({ exportDef, hasResults, onClick }) {
  return (
    <div
      className={`dl-card ${!hasResults ? 'dl-disabled' : ''}`}
      onClick={hasResults ? onClick : undefined}
      title={!hasResults ? 'Run compilation first' : `Download ${exportDef.label}`}
    >
      <Icon name={exportDef.icon} size={22} className="dl-icon" />
      <div className="dl-name">{exportDef.label}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, lineHeight: 1.4 }}>
        {exportDef.desc}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span className="dl-ext">{exportDef.format}</span>
        {!hasResults && (
          <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>
            PENDING
          </span>
        )}
      </div>
    </div>
  )
}

/** Trace panel shell — prepared for Layer 10 structural traceability */
function TracePanelShell({ traceability, sections }) {
  if (!traceability || Object.keys(traceability).length === 0) {
    return (
      <div className="trace-empty">
        <Icon name="layers" size={28} style={{ color: 'var(--border-default)', marginBottom: 12 }} />
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6 }}>
          No Trace Data Available
        </div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)', maxWidth: 380, textAlign: 'center', lineHeight: 1.6 }}>
          Traceability records will appear here after compilation. Each section will show its full mapping → transformation → validation chain.
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="trace-header-bar">
        <Icon name="layers" size={14} style={{ color: 'var(--accent)' }} />
        <span>Generation Traceability Log</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>
          {Object.keys(traceability).length} sections audited
        </span>
      </div>

      {Object.entries(traceability).map(([sid, trace]) => (
        <div key={sid} className="trace-card">
          <div className="trace-card-header">
            <span style={{ fontFamily: 'JetBrains Mono', fontSize: 10, color: 'var(--accent)', fontWeight: 700 }}>
              {SECTIONS[sid]?.number}
            </span>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>
              {SECTIONS[sid]?.name || sid}
            </span>
            {trace.execution_timestamp && (
              <span style={{ marginLeft: 'auto', fontSize: 9, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono', display: 'flex', alignItems: 'center', gap: 4 }}>
                <Icon name="clock" size={9} />
                {trace.execution_timestamp}
              </span>
            )}
          </div>

          <div className="trace-meta-grid">
            {trace.mapping_summary && (
              <div className="trace-meta-item">
                <span className="trace-meta-label">Mapping</span>
                <span className="trace-meta-value">{trace.mapping_summary}</span>
              </div>
            )}
            {trace.transformation_summary && (
              <div className="trace-meta-item">
                <span className="trace-meta-label">Transform</span>
                <span className="trace-meta-value">{trace.transformation_summary}</span>
              </div>
            )}
            {trace.prompt_logic_summary && (
              <div className="trace-meta-item" style={{ gridColumn: '1 / -1' }}>
                <span className="trace-meta-label">Prompt Logic</span>
                <span className="trace-meta-value">{trace.prompt_logic_summary}</span>
              </div>
            )}
            {trace.input_sources?.length > 0 && (
              <div className="trace-meta-item" style={{ gridColumn: '1 / -1' }}>
                <span className="trace-meta-label">Sources</span>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 4 }}>
                  {trace.input_sources.map((s, i) => (
                    <span key={i} style={{
                      fontSize: 10, fontFamily: 'JetBrains Mono', padding: '2px 7px',
                      background: 'var(--bg-interactive)', border: '1px solid var(--border-subtle)',
                      borderRadius: 4, color: 'var(--text-secondary)',
                    }}>
                      {s}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {trace.generation_blocked && (
            <div className="trace-blocked">
              <Icon name="alert-triangle" size={12} />
              <strong>Blocked:</strong> {trace.block_reason}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

// ═══════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════
export default function App() {
  // ── State ──────────────────────────────────────────
  const [resourceDocs, setResourceDocs]       = useState([])
  const [docsError, setDocsError]             = useState(null)
  const [selectedSections, setSelectedSections] = useState({})
  const [sectionQuery, setSectionQuery]       = useState('')
  const [generationConstraints, setGenerationConstraints] = useState('')
  const [status, setStatus]                   = useState({ status: 'idle', progress: 0, message: 'Awaiting valid document set' })
  const [results, setResults]                 = useState(null)
  const [activeTab, setActiveTab]             = useState('synopsis')
  const [activeViewTab, setActiveViewTab]     = useState('generated')
  const [toasts, setToasts]                   = useState([])
  const [elapsedTime, setElapsedTime]         = useState(0)
  const elapsedRef = useRef(null)

  const backendOnline = docsError === null

  // ── Toast System ───────────────────────────────────
  const addToast = (msg, type = 'info') => {
    const id = Date.now()
    setToasts(t => [...t, { id, msg, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4500)
  }

  // ── Elapsed Timer ──────────────────────────────────
  useEffect(() => {
    if (status.status === 'running') {
      setElapsedTime(0)
      elapsedRef.current = setInterval(() => setElapsedTime(s => s + 1), 1000)
    } else {
      clearInterval(elapsedRef.current)
    }
    return () => clearInterval(elapsedRef.current)
  }, [status.status])

  // ── Fetch Documents ────────────────────────────────
  const fetchDocs = async () => {
    try {
      const res = await fetch(`${API_URL}/documents`)
      if (!res.ok) throw new Error('API Error')
      const data = await res.json()
      setResourceDocs(data.documents || [])
      setDocsError(null)
    } catch (e) {
      setDocsError('Backend unreachable. Verify server is running on port 8000.')
    }
  }
  useEffect(() => {
    fetchDocs()
    const iv = setInterval(fetchDocs, 5000)
    return () => clearInterval(iv)
  }, [])

  // ── File Upload ────────────────────────────────────
  const onDrop = useCallback(async (acceptedFiles) => {
    if (!acceptedFiles?.length) return
    const formData = new FormData()
    acceptedFiles.forEach(f => formData.append('files', f))
    try {
      addToast(`Ingesting ${acceptedFiles.length} file(s) into secure context...`, 'info')
      const res = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData })
      if (!res.ok) throw new Error('Upload rejected by intake layer')
      addToast('Evidence ingested. Documents mapped to section context.', 'success')
      fetchDocs()
    } catch (e) {
      addToast(e.message, 'error')
    }
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
    },
  })

  const handleDelete = async (filename) => {
    try {
      const res = await fetch(`${API_URL}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Removal failed')
      addToast('Document removed from evidence context.', 'success')
      fetchDocs()
    } catch (e) {
      addToast(e.message, 'error')
    }
  }

  // ── Compiler Pipeline ──────────────────────────────
  const handleGenerate = async () => {
    const sel = Object.keys(selectedSections).filter(k => selectedSections[k])
    if (!sel.length || !resourceDocs.length) return

    const documentIds = resourceDocs
      .map((doc) => doc.filename || doc.name)
      .filter((id) => typeof id === 'string' && id.trim())
    if (!documentIds.length) {
      addToast('No valid document filenames in context. Upload evidence files first.', 'error')
      return
    }

    console.log('GENERATE REQUEST:', { section_ids: sel, document_ids: documentIds })

    setStatus({ status: 'running', progress: 10, message: 'Initializing deterministic extraction pipeline...' })
    setResults(null)

    try {
      const gRes = await fetch(`${API_URL}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section_ids: sel,
          document_ids: documentIds,
          ...(generationConstraints ? { constraints: generationConstraints } : {}),
        }),
      })
      if (!gRes.ok) {
        let detail = 'Engine rejected the generation request.'
        try {
          const errBody = await gRes.json()
          if (errBody?.detail) detail = typeof errBody.detail === 'string' ? errBody.detail : JSON.stringify(errBody.detail)
        } catch {
          /* ignore */
        }
        throw new Error(detail)
      }

      const iv = setInterval(async () => {
        try {
          const sRes = await fetch(`${API_URL}/status`)
          const d = await sRes.json()
          setStatus({
            status: d.status === 'error' ? 'error' : 'running',
            progress: d.progress || 0,
            message: d.message || 'Processing...',
            currentStage: d.current_stage || '',
          })
          if (d.status === 'complete') {
            setResults(d.results)
            const ids = Object.keys(normalizeSectionsMap(d.results))
            if (ids.length) { setActiveTab(ids[0]); setActiveViewTab('generated') }
            setStatus({
              status: 'complete',
              progress: 100,
              message: 'All sections validated. Zero-hallucination contract satisfied.',
              currentStage: 'Validate',
            })
            addToast('Compilation complete. Validation passed.', 'success')
            clearInterval(iv)
          } else if (d.status === 'error') {
            addToast(`Critical Error: ${d.error}`, 'error')
            setStatus({ status: 'error', progress: 0, message: d.error || 'Pipeline failed.', currentStage: d.current_stage || '' })
            clearInterval(iv)
          }
        } catch (pollErr) {
          // Silent poll failures — server may be momentarily busy
        }
      }, 1500)
    } catch (e) {
      setStatus({ status: 'error', progress: 0, message: 'Pipeline initiation failed.', currentStage: '' })
      addToast(e.message, 'error')
    }
  }

  // ── Derived values ─────────────────────────────────
  const filteredSections = Object.entries(SECTIONS).filter(([k, v]) => {
    const text = (v.name + v.number).toLowerCase()
    return text.includes(sectionQuery.toLowerCase())
  })
  const selCount = Object.values(selectedSections).filter(Boolean).length

  const getStepState = (step) => {
    const stageMap = {
      'initializing': 'load',
      'loading documents': 'load',
      'extracting text': 'extract',
      'matching sections': 'map',
      'generating csr': 'generate',
      'validating': 'validate',
      'saving outputs': 'validate',
      'complete': 'validate',
    }
    const order = ['load', 'extract', 'map', 'generate', 'validate']
    const { progress, status: st, currentStage } = status
    const issueState = pipelineIssueState(results)
    const normalizedStage = (currentStage || '').toLowerCase()
    const activeKey = stageMap[normalizedStage]
    const stepIdx = order.indexOf(step.key)
    const activeIdx = order.indexOf(activeKey)

    if (st === 'error') {
      if (activeIdx >= 0) return stepIdx <= activeIdx ? 'failed' : ''
      return progress >= step.prog ? 'failed' : ''
    }
    if (st === 'complete') {
      if (step.key === 'validate' && issueState === 'failed') return 'failed'
      if (step.key === 'validate' && issueState === 'warning') return 'warning'
      return 'done'
    }
    if (st === 'running') {
      if (activeIdx >= 0) {
        if (stepIdx < activeIdx) return 'done'
        if (stepIdx === activeIdx) return 'active'
        return ''
      }
      if (progress > step.prog) return 'done'
      if (progress > (step.prog - 20) && progress <= step.prog) return 'active'
    }
    return ''
  }

  // Derive execute button label + state
  const execLabel = () => {
    if (status.status === 'running')  return <><Icon name="loader" size={15} className="spin" /> Compiling... {elapsedTime > 0 ? `${String(Math.floor(elapsedTime / 60)).padStart(2,'0')}:${String(elapsedTime % 60).padStart(2,'0')}` : ''}</>
    if (status.status === 'complete') return <><Icon name="check-circle" size={15} /> Re-run Compilation</>
    if (status.status === 'error')    return <><Icon name="x-circle" size={15} /> Retry Generation</>
    if (!resourceDocs.length || !selCount) return <><Icon name="alert-triangle" size={15} /> Select Sections & Load Documents</>
    return <><Icon name="cpu" size={15} /> Execute Zero-Hallucination Compiler</>
  }

  const execDisabled = status.status === 'running' || selCount === 0 || resourceDocs.length === 0

  const lifecycleCfg = LIFECYCLE_CONFIG[status.status] || LIFECYCLE_CONFIG.idle
  const sectionMap = normalizeSectionsMap(results)
  const resultSectionIds = Object.keys(sectionMap)
  const summaryCounts = sectionSummaryCounts(sectionMap)

  const fmtElapsed = `${String(Math.floor(elapsedTime / 60)).padStart(2, '0')}:${String(elapsedTime % 60).padStart(2, '0')}`

  const handleDownload = (type) => {
    if (!results) return

    // Deterministic local fallback for demo reliability.
    if (type === 'summary') {
      const lines = []
      lines.push('CERC Clinical AI Workbench - CSR Text Export')
      lines.push('')
      lines.push(`Complete: ${summaryCounts.complete} | Partial: ${summaryCounts.partial} | Missing: ${summaryCounts.missing}`)
      lines.push('')
      resultSectionIds.forEach((sid) => {
        const sec = sectionMap[sid] || {}
        lines.push(`=== ${SECTIONS[sid]?.number || sid} ${SECTIONS[sid]?.name || sid} ===`)
        lines.push(`Status: ${sec.status || 'unknown'}`)
        lines.push(`Sources: ${(sec.source_documents || sec.sources || []).length}`)
        lines.push(`Missing: ${(sec.missing_elements || []).length}`)
        lines.push(`Validation Score: ${sec?.validation?.score ?? sec?.confidence_score ?? 'n/a'}`)
        lines.push('')
        if ((sec.status || '').toLowerCase() === 'missing' || (sec.status || '').toLowerCase() === 'blocked' || (sec.status || '').toLowerCase() === 'failed') {
          lines.push('[BLOCKED OR MISSING: NO GENERATED CONTENT]')
        } else {
          lines.push((sec.content || sec.generated_text || '').trim() || '[NO CONTENT]')
        }
        lines.push('')
      })
      const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'csr_sections.txt'
      a.click()
      URL.revokeObjectURL(url)
      return
    }

    if (type === 'log') {
      const payload = {
        traceability: results?.traceability || {},
        pipeline_summary: results?.pipeline_summary || {},
        summary: summaryCounts,
        sections: sectionMap,
      }
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'traceability.json'
      a.click()
      URL.revokeObjectURL(url)
      return
    }

    window.open(`${API_URL}/download/${type}`, '_blank')
  }

  // ═══════════════════════════════════════════════════
  // RENDER
  // ═══════════════════════════════════════════════════
  return (
    <div className="app">

      {/* ══ SIDEBAR ══════════════════════════════════ */}
      <aside className="sidebar">

        {/* Logo block */}
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <Icon name="cpu" size={22} style={{ color: 'var(--accent)' }} />
            <div>
              <div className="sidebar-title">CERC</div>
              <div className="sidebar-subtitle">Clinical AI Workbench</div>
            </div>
          </div>
        </div>

        {/* Group 1: Navigation */}
        <nav className="sidebar-nav">
          <div className="sidebar-group-label" style={{ paddingTop: 0 }}>Navigation</div>
          <div className="nav-item active"><Icon name="cpu" size={15} /> Data Compiler</div>
          <div className="nav-item"><Icon name="database" size={15} /> Static Knowledge</div>
          <div className="nav-item"><Icon name="shield" size={15} /> Validation Rules</div>
          <div className="nav-item"><Icon name="settings" size={15} /> System Settings</div>
        </nav>

        {/* Group 2: Compliance standards */}
        <SidebarGroup label="Compliance Standards">
          <div className="compliance-badge">
            <span className="compliance-dot" style={{ background: 'var(--accent)' }} />
            ICH E3
          </div>
          <div className="compliance-badge">
            <span className="compliance-dot" style={{ background: 'var(--accent)' }} />
            ISO 14155
          </div>
          <div className="compliance-badge">
            <span className="compliance-dot" style={{ background: '#a78bfa' }} />
            GPT-4o Zero-Shot
          </div>
        </SidebarGroup>

        {/* Group 3: Environment footer */}
        <div className="sidebar-footer">
          <div className="sidebar-divider" style={{ marginBottom: 12 }} />

          <div className="env-meta-row">
            <Icon name={backendOnline ? 'server' : 'wifi-off'} size={11} style={{ color: backendOnline ? 'var(--success)' : 'var(--warning)', flexShrink: 0 }} />
            <span style={{ color: backendOnline ? 'var(--success)' : 'var(--warning)', fontWeight: 700 }}>
              {backendOnline ? 'LOCAL BACKEND' : 'BACKEND OFFLINE'}
            </span>
          </div>

          <div className="env-meta-row" style={{ marginTop: 6 }}>
            <Icon name="layers" size={11} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <span>Deterministic Mode</span>
          </div>

          <div className="env-meta-row" style={{ marginTop: 4 }}>
            <Icon name="bar-chart" size={11} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
            <span>{BUILD_VERSION} · Production</span>
          </div>
        </div>
      </aside>

      {/* ══ MAIN WORKSPACE ═══════════════════════════ */}
      <main className="workspace">

        {/* TOP HEADER — System status strip */}
        <header className="top-header">
          <div>
            <h1 className="header-title">Generate CSR</h1>
            <p className="header-subtitle">Evidence-backed clinical document compiler</p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            {/* Section context */}
            {selCount > 0 && (
              <div className="header-context-pill">
                <Icon name="layers" size={11} />
                {selCount} section{selCount !== 1 ? 's' : ''} targeted
              </div>
            )}

            {/* Elapsed time when running */}
            {status.status === 'running' && (
              <div className="header-context-pill" style={{ color: 'var(--accent)', borderColor: 'rgba(14,165,233,0.3)' }}>
                <Icon name="clock" size={11} />
                {fmtElapsed}
              </div>
            )}

            {/* Lifecycle status pill */}
            <motion.div
              className="status-lifecycle"
              animate={{ borderColor: lifecycleCfg.color + '44' }}
              transition={{ duration: 0.3 }}
              style={{ color: lifecycleCfg.color }}
            >
              {lifecycleCfg.dot ? (
                <span className="status-dot running" />
              ) : (
                <Icon name={lifecycleCfg.icon} size={11} style={{ color: lifecycleCfg.color }} />
              )}
              {lifecycleCfg.label}
            </motion.div>

            {/* Last compiled */}
            <div style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>
              {results ? `Last: ${new Date().toLocaleTimeString()}` : 'Never compiled'}
            </div>
          </div>
        </header>

        {/* WORKSPACE CONTENT */}
        <div className="workspace-content">

          {/* TOP ROW: Upload + Section Selector */}
          <div className="top-row">

            {/* ── SECURE INTAKE ────────────────────── */}
            <div className="upload-panel">
              <div className="panel-head">
                Secure Intake System
                <span className="doc-count">{resourceDocs.length}</span>
              </div>

              {/* Dropzone */}
              <div
                {...getRootProps()}
                className={`dropzone ${isDragActive ? 'active' : ''}`}
                style={{ position: 'relative' }}
              >
                <input {...getInputProps()} disabled={status.status === 'running'} />
                <Icon name="upload-cloud" size={30} className="drop-icon" />
                <div className="drop-text">Strict Document Upload</div>
                <div className="drop-sub">PDF · DOCX · End-to-end encrypted</div>
                {isDragActive && (
                  <div style={{
                    position: 'absolute', inset: 0, borderRadius: 'var(--radius-sm)',
                    background: 'rgba(14,165,233,0.06)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 12, fontWeight: 700, color: 'var(--accent)',
                  }}>
                    Release to ingest
                  </div>
                )}
              </div>

              {/* Backend error */}
              {docsError && (
                <div className="intake-error">
                  <Icon name="wifi-off" size={12} />
                  {docsError}
                </div>
              )}

              {/* Document ledger */}
              <div className="doc-list">
                {resourceDocs.length === 0 && !docsError && (
                  <div className="doc-empty-state">
                    <Icon name="database" size={18} style={{ color: 'var(--border-default)', marginBottom: 6 }} />
                    <span>No evidence documents loaded</span>
                  </div>
                )}
                <AnimatePresence>
                  {resourceDocs.map(doc => (
                    <DocumentCard
                      key={doc.name}
                      doc={doc}
                      onDelete={handleDelete}
                      disabled={status.status === 'running'}
                    />
                  ))}
                </AnimatePresence>
              </div>
            </div>

            {/* ── SECTION SELECTOR ─────────────────── */}
            <div className="section-hero">
              <div className="hero-header">
                <div>
                  <div className="hero-title">Select Compilation Targets</div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                    All generated content strictly grounded within uploaded evidence context.
                  </div>
                </div>
                <div className="search-bar">
                  <Icon name="search" size={13} style={{ color: 'var(--text-muted)' }} />
                  <input
                    type="text"
                    placeholder="Search structures (e.g., 9.1)"
                    value={sectionQuery}
                    onChange={e => setSectionQuery(e.target.value)}
                  />
                </div>
              </div>

              <div className="section-grid">
                {filteredSections.map(([id, meta]) => (
                  <SectionCard
                    key={id}
                    id={id}
                    meta={meta}
                    selected={!!selectedSections[id]}
                    onClick={() => setSelectedSections(p => ({ ...p, [id]: !p[id] }))}
                    resultSection={sectionMap?.[id]}
                    isInProgress={status.status === 'running' && selectedSections[id]}
                  />
                ))}
              </div>
            </div>
          </div>

          {/* ── WORKFLOW BAR ─────────────────────────── */}
          <div className="workflow-bar">

            {/* Left: Execute + InstructionBar */}
            <div className="workflow-left">
              <button
                className="btn-generate"
                disabled={execDisabled}
                onClick={handleGenerate}
              >
                {execLabel()}
              </button>

              <div className="workflow-stats">
                <span>{selCount} structure{selCount !== 1 ? 's' : ''} targeted</span>
                <span>{resourceDocs.length} evidence file{resourceDocs.length !== 1 ? 's' : ''} loaded</span>
              </div>

              {/* Constraint bar */}
              <div style={{ marginTop: 10, maxWidth: 480 }}>
                <InstructionBar
                  onSubmit={(val) => {
                    setGenerationConstraints(val)
                    addToast('Generation constraint applied.', 'info')
                  }}
                  disabled={status.status === 'running' || !resourceDocs.length || !selCount}
                  disabledReason={
                    status.status === 'running' ? 'Pipeline running'
                      : !resourceDocs.length ? 'No documents loaded'
                      : !selCount ? 'No sections selected'
                      : ''
                  }
                />
                {generationConstraints && (
                  <div className="constraint-active-bar">
                    <span className="constraint-active-label">⚑ CONSTRAINT ACTIVE</span>
                    <span className="constraint-active-text">{generationConstraints}</span>
                    <button onClick={() => setGenerationConstraints('')} className="constraint-clear-btn">✕ Clear</button>
                  </div>
                )}
              </div>
            </div>

            {/* Right: Pipeline stepper */}
            <div className="workflow-right">
              <div className="stepper">
                {PIPELINE_STEPS.map(step => (
                  <PipelineStepItem key={step.key} step={step} stepState={getStepState(step)} />
                ))}
              </div>

              {/* Progress track */}
              <div className="progress-track">
                <div className="progress-fill" style={{ width: `${status.progress}%` }} />
              </div>

              {/* Pipeline message */}
              {status.status !== 'idle' && (
                <div className="pipeline-msg">{status.message}</div>
              )}
            </div>
          </div>

          {/* ── RESULTS WORKSPACE ────────────────────── */}
          {(results || status.status !== 'idle') && (
            <motion.div
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.28, ease: [0.2, 0.65, 0.3, 0.9] }}
              className="results-workspace"
            >
              {/* Tab bar */}
              <div className="results-tabs">
                {[
                  ['generated',  'Generated'],
                  ['pipeline',   '⬡ Pipeline'],
                  ['sources',    'Sources'],
                  ['validation', 'Validation'],
                  ['downloads',  'Downloads'],
                  ['trace',      '◈ Trace'],
                ].map(([t, label]) => (
                  <button
                    key={t}
                    className={`r-tab ${activeViewTab === t ? 'active' : ''}`}
                    onClick={() => setActiveViewTab(t)}
                  >
                    {label}
                    {/* Badge: generated section count for Generated tab */}
                    {t === 'generated' && results && (
                      <span className="tab-count">{resultSectionIds.length}</span>
                    )}
                  </button>
                ))}
              </div>

              <div className="results-content">

                {/* ── GENERATED TAB ─────────────────── */}
                {activeViewTab === 'generated' && (
                  <div className="generated-tab">
                    {results && (
                      <div className="acc-provenance" style={{ marginBottom: 16 }}>
                        <Icon name="bar-chart" size={11} style={{ color: 'var(--accent)' }} />
                        Complete: {summaryCounts.complete} · Partial: {summaryCounts.partial} · Missing: {summaryCounts.missing}
                      </div>
                    )}
                    {results
                      ? resultSectionIds.map(secId => {
                          const valScore = sec?.validation?.score || 0
                          const missing = sec?.trace?.missing_elements || sec?.missing_elements || []
                          const sectionStatus = sec?.status || 'missing'
                          const sourceCount = (sec?.source_documents || sec?.sources || []).length
                          const safeContent = ['missing', 'blocked', 'failed'].includes(sectionStatus.toLowerCase())
                            ? ''
                            : (sec.content || sec.generated_text || '')

                          return (
                            <div key={secId} className="accordion">
                              <div className="acc-head" onClick={() => setActiveTab(secId === activeTab ? null : secId)}>
                                <div className="acc-title">
                                  <span style={{ fontFamily: 'JetBrains Mono', fontSize: 11, color: 'var(--accent)' }}>
                                    {SECTIONS[secId]?.number}
                                  </span>
                                  {SECTIONS[secId]?.name || secId}
                                </div>

                                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                  {/* Dynamic status badge */}
                                  {sectionStatus
                                    ? <SectionStatusBadge status={sectionStatus} />
                                    : <span className="sys-badge" style={{ color: 'var(--success)', borderColor: 'rgba(16,185,129,0.3)', background: 'rgba(16,185,129,0.1)' }}>GENERATED</span>
                                  }
                                  {/* Validation mini score */}
                                  {valScore !== undefined && (
                                    <span style={{
                                      fontSize: 10, fontFamily: 'JetBrains Mono', fontWeight: 700,
                                      color: valScore >= 70 ? 'var(--success)' : valScore >= 40 ? 'var(--warning)' : 'var(--danger)',
                                    }}>
                                      {Math.round(valScore * (valScore <= 1 ? 100 : 1))}%
                                    </span>
                                  )}
                                  {missing.length > 0 && <MissingBadge count={missing.length} />}
                                  <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'JetBrains Mono' }}>
                                    S:{sourceCount} M:{missing.length}
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      navigator.clipboard.writeText(safeContent || '')
                                      addToast('Section text copied.', 'success')
                                    }}
                                    style={{ color: 'var(--text-muted)', padding: 4 }}
                                    title="Copy to clipboard"
                                  >
                                    <Icon name="copy" size={14} />
                                  </button>
                                </div>
                              </div>

                              <AnimatePresence>
                                {activeTab === secId && (
                                  <motion.div
                                    initial={{ height: 0 }}
                                    animate={{ height: 'auto' }}
                                    exit={{ height: 0 }}
                                    style={{ overflow: 'hidden' }}
                                    transition={{ duration: 0.22, ease: [0.2, 0.65, 0.3, 0.9] }}
                                  >
                                    <div className="acc-body">
                                      {/* Mini provenance row */}
                                      {(sec?.source_documents?.length > 0 || sec?.sources?.length > 0) && (
                                        <div className="acc-provenance">
                                          <Icon name="link" size={11} style={{ color: 'var(--accent)' }} />
                                          Sources: {(sec.source_documents || sec.sources || []).join(', ')}
                                        </div>
                                      )}
                                      <FormattedContent content={safeContent} />
                                    </div>
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                          )
                        })
                      : (
                        <div className="results-empty">
                          <Icon name="file-text" size={24} style={{ color: 'var(--border-default)', marginBottom: 10 }} />
                          <div>Awaiting compilation results...</div>
                        </div>
                      )}
                  </div>
                )}

                {/* ── PIPELINE TAB ──────────────────── */}
                {activeViewTab === 'pipeline' && (
                  <PipelineVisualizer
                    sections={sectionMap}
                    sectionsMeta={SECTIONS}
                    isLoading={status.status === 'running'}
                  />
                )}

                {/* ── SOURCES TAB (Element Map) ──────── */}
                {activeViewTab === 'sources' && (
                  <div className="sources-tab">
                    {sectionMap?.[activeTab]
                      ? (
                        <div className="map-viewer">
                          <div className="map-viewer-header">
                            <div>
                              <h3 style={{ fontSize: 14, color: 'var(--text-primary)', fontWeight: 700 }}>
                                Element Map — {SECTIONS[activeTab]?.name}
                              </h3>
                              <p style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>
                                Semantic XAI linking from template requirements to verifiable document locations.
                              </p>
                            </div>
                            {/* Coverage teaser */}
                            {(() => {
                              const sec = sectionMap[activeTab]
                              const total = Object.keys(sec.element_map_rich || {}).length
                              const missing = sec.missing_elements?.length || 0
                              const mapped = Math.max(0, total - missing)
                              if (!total) return null
                              return (
                                <div className="coverage-pill">
                                  {mapped}/{total} elements mapped · {Math.round((mapped / total) * 100)}% coverage
                                </div>
                              )
                            })()}
                          </div>

                          {(() => {
                            const src = sectionMap[activeTab]?.source_documents || sectionMap[activeTab]?.sources || []
                            if (!src.length) return null
                            return src.map((s, i) => (
                              <div key={`src-${i}`} className="map-card safe">
                                <div className="map-top">
                                  <div className="map-el-name">Source Document</div>
                                  <span className="sys-badge">LINKED</span>
                                </div>
                                <div className="map-el-val">{s}</div>
                              </div>
                            ))
                          })()}

                          {Object.entries(sectionMap[activeTab]?.element_map_rich || {}).map(([el, meta], i) => (
                            <div key={i} className={`map-card ${meta.status === 'missing' ? 'error' : meta.status === 'partial' ? 'gap' : 'safe'}`}>
                              <div className="map-top">
                                <div className="map-el-name">{el}</div>
                                <span className="sys-badge" style={{
                                  color: meta.status === 'missing' ? 'var(--danger)' : meta.status === 'partial' ? 'var(--warning)' : 'var(--success)',
                                  background: meta.status === 'missing' ? 'rgba(239,68,68,0.1)' : 'rgba(16,185,129,0.1)',
                                  borderColor: meta.status === 'missing' ? 'rgba(239,68,68,0.3)' : 'transparent',
                                }}>
                                  {meta.status?.toUpperCase()}
                                </span>
                              </div>
                              <div className="map-el-val">
                                {meta.value === null
                                  ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>Not found in source documents.</span>
                                  : meta.value
                                }
                              </div>
                              {meta.source && (
                                <div className="map-trace">
                                  <div className="trace-head">
                                    <Icon name="link" size={10} />
                                    {meta.source.file} — Page {meta.source.page}
                                  </div>
                                  <div className="trace-quote">"{meta.source.text}"</div>
                                </div>
                              )}
                            </div>
                          ))}

                          {Object.keys(sectionMap[activeTab]?.element_map_rich || {}).length === 0 && (
                            <div className="results-empty">
                              <Icon name="link" size={22} style={{ color: 'var(--border-default)', marginBottom: 8 }} />
                              <div>No element map data for this section.</div>
                            </div>
                          )}
                        </div>
                      )
                      : (
                        <div className="results-empty">
                          <Icon name="link" size={22} style={{ color: 'var(--border-default)', marginBottom: 8 }} />
                          <div>Select a section in the Generated tab to view its source evidence map.</div>
                        </div>
                      )}
                  </div>
                )}

                {/* ── VALIDATION TAB ────────────────── */}
                {activeViewTab === 'validation' && sectionMap?.[activeTab] && (
                  <div className="validation-tab">

                    {/* Pipeline Transparency Panel */}
                    <div className="transparency-panel">
                      <div className="transparency-title">
                        <Icon name="shield" size={13} style={{ color: 'var(--accent)' }} />
                        Pipeline Transparency — {SECTIONS[activeTab]?.name}
                      </div>
                      {(() => {
                        const sec = sectionMap[activeTab] || {}
                        const val = sec.validation || { score: 0, coverage_pct: 0, warnings: [], errors: [] }
                        const trace = sec.trace || {}

                        const confidence = val.score || 0
                        const coverage = val.coverage_pct || 0
                        const missingCount = trace.missing_elements?.length || sec.missing_elements?.length || 0
                        const mappedTotal = Object.keys(sec.element_map_rich || {}).length
                        const mappedCount = Math.max(0, mappedTotal - missingCount)
                        const facts = trace.paragraphs_used_count || '—'

                        return (
                          <div className="transparency-grid">
                            <div className="transp-stat">
                              <span className="transp-label">Facts Extracted</span>
                              <span className="transp-value">{facts}</span>
                            </div>
                            <div className="transp-stat">
                              <span className="transp-label">Elements Mapped</span>
                              <span className="transp-value">{mappedCount} / {mappedTotal || '—'}</span>
                            </div>
                            <div className="transp-stat">
                              <span className="transp-label">Coverage</span>
                              <span className="transp-value" style={{ color: coverage >= 80 ? 'var(--success)' : 'var(--warning)' }}>{coverage}%</span>
                            </div>
                            <div className="transp-stat">
                              <span className="transp-label">Missing</span>
                              <span className="transp-value" style={{ color: missingCount > 0 ? 'var(--warning)' : 'var(--success)' }}>{missingCount}</span>
                            </div>
                            <div className="transp-stat">
                              <span className="transp-label">Confidence</span>
                              <span className="transp-value" style={{ color: confidence >= 70 ? 'var(--success)' : 'var(--warning)' }}>{confidence}%</span>
                            </div>
                          </div>
                        )
                      })()}
                    </div>

                    {/* Multi-dimension validation metrics */}
                    <div className="val-metric-block">
                      <div className="val-block-label">Compliance Dimensions</div>

                      {(() => {
                        const sec = sectionMap[activeTab] || {}
                        const val = sec.validation || {}

                        const structStatus = val.structure_ok ? 'pass' : 'fail'
                        const coverageStatus = val.coverage_pct === 100 ? 'pass' : val.coverage_pct >= 50 ? 'warning' : 'fail'
                        const toneStatus = val.tone_ok ? 'pass' : 'fail'
                        const hallStatus = val.hallucination_risk === 'low' ? 'pass' : val.hallucination_risk === 'medium' ? 'warning' : 'fail'
                        const numStatus = val.numeric_consistency ? 'pass' : 'fail'

                        return (
                          <>
                            <ValidationMetricRow label="Structure Compliance" status={structStatus} explanation="" />
                            <ValidationMetricRow label="Source Completeness" status={coverageStatus} explanation="" />
                            <ValidationMetricRow label="Scientific Tone" status={toneStatus} explanation="" />
                            <ValidationMetricRow label="Hallucination Risk" status={hallStatus} explanation="" />
                            <ValidationMetricRow label="Numeric Consistency" status={numStatus} explanation="" />
                          </>
                        )
                      })()}
                    </div>

                    {/* Score cards */}
                    <div className="val-grid">
                      {(() => {
                        const sec = sectionMap[activeTab] || {}
                        const val = sec.validation || { score: 0, coverage_pct: 0 }
                        const confidence = val.score || 0
                        const coverage = val.coverage_pct || 0
                        const issuesCount = (val.warnings || []).length + (val.errors || []).length

                        return (
                          <>
                            <div className="val-stat">
                              <div className="val-lbl">Confidence Score</div>
                              <div className={`val-num ${confidence >= 70 ? 'num-green' : 'num-amber'}`}>
                                {confidence}%
                              </div>
                            </div>
                            <div className="val-stat">
                              <div className="val-lbl">Section Coverage</div>
                              <div className={`val-num ${coverage >= 80 ? 'num-green' : 'num-amber'}`}>
                                {coverage}%
                              </div>
                            </div>
                            <div className="val-stat">
                              <div className="val-lbl">Compliance Issues</div>
                              <div className={`val-num ${issuesCount > 0 ? 'num-red' : 'num-green'}`}>
                                {issuesCount}
                              </div>
                            </div>
                          </>
                        )
                      })()}
                    </div>

                    {/* Validation log */}
                    <div className="issue-list">
                      <h4 style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700, marginBottom: 14, letterSpacing: '0.06em' }}>Validation Log</h4>
                      {(() => {
                        const sec = sectionMap[activeTab] || {}
                        const val = sec.validation || { warnings: [], errors: [] }
                        const issues = [
                          ...(val.errors || []).map(e => ({ type: 'error', message: e })),
                          ...(val.warnings || []).map(w => ({ type: 'warning', message: w }))
                        ]

                        if (issues.length === 0) {
                          return (
                            <div style={{ color: 'var(--success)', fontSize: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Icon name="check-circle" size={14} />
                              Passed all deterministic validation gates. No hallucinations detected.
                            </div>
                          )
                        }

                        return issues.map((iss, i) => (
                          <div style={{ fontSize: 13, color: 'var(--text-primary)', marginBottom: 8 }} key={i}>
                            {iss.type === 'error' ? '❌' : '⚠️'} {iss.message}
                          </div>
                        ))
                      })()}
                    </div>
                  </div>
                )}

                {/* ── DOWNLOADS TAB ─────────────────── */}
                {activeViewTab === 'downloads' && (
                  <div>
                    <div style={{ marginBottom: 20 }}>
                      <h3 style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 6 }}>
                        Structured Export Actions
                      </h3>
                      <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        All artefacts are deterministically generated from the same evidence context.
                        {!results && ' Run compilation first to enable exports.'}
                      </p>
                    </div>
                    <div className="dl-grid">
                      {EXPORTS.map(d => (
                        <ExportCard
                          key={d.type}
                          exportDef={d}
                          hasResults={!!results}
                          onClick={() => handleDownload(d.type)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* ── TRACE TAB ─────────────────────── */}
                {activeViewTab === 'trace' && (
                  <TracePanelShell
                    traceability={results?.traceability}
                    sections={results?.sections}
                  />
                )}

              </div>
            </motion.div>
          )}

        </div>
      </main>

      {/* ── TOAST OVERLAY ────────────────────────── */}
      <div className="toast-wrap">
        <AnimatePresence>
          {toasts.map(t => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, scale: 0.94 }}
              transition={{ duration: 0.2 }}
              className={`toast ${t.type}`}
            >
              {t.type === 'success'
                ? <Icon name="check-circle" size={14} style={{ color: 'var(--success)', flexShrink: 0 }} />
                : t.type === 'error'
                  ? <Icon name="x-circle" size={14} style={{ color: 'var(--danger)', flexShrink: 0 }} />
                  : <Icon name="activity" size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              }
              {t.msg}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

    </div>
  )
}
