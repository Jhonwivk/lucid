import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError, importProjectMaterial, startAnalysis } from '../api/client'
import { useI18n } from '../i18n'

type NewAnalysisDialogProps = {
  open: boolean
  onClose: () => void
}

const ACCEPTED_FILES = '.txt,.md,.markdown,.pdf,.csv,.xlsx,.png,.jpg,.jpeg,.json,.docx,.pptx'

export function NewAnalysisDialog({ open, onClose }: NewAnalysisDialogProps) {
  const { locale } = useI18n()
  const navigate = useNavigate()
  const isZh = locale === 'zh-CN'
  const id = useId()
  const dialogRef = useRef<HTMLDialogElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // Refs protect the create/upload boundary even before React renders again.
  const busyRef = useRef(false)
  const projectIdRef = useRef<string | null>(null)
  const uploadedCountRef = useRef(0)
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')
  const [text, setText] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [dragging, setDragging] = useState(false)
  const [creating, setCreating] = useState(false)
  const [projectId, setProjectId] = useState<string | null>(null)
  const [uploadedCount, setUploadedCount] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open && !creating) dialog.close()
  }, [open, creating])

  function requestClose() {
    if (!busyRef.current) onClose()
  }

  function addFiles(incoming: File[]) {
    if (busyRef.current || projectIdRef.current) return
    setFiles((current) => {
      const next = [...current]
      for (const file of incoming) {
        if (!next.some((item) => item.name === file.name && item.size === file.size && item.lastModified === file.lastModified)) {
          next.push(file)
        }
      }
      return next
    })
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busyRef.current || !title.trim() || !question.trim()) return
    busyRef.current = true
    setCreating(true)
    setError(null)
    try {
      let currentProjectId = projectIdRef.current
      if (!currentProjectId) {
        const created = await startAnalysis({
          title: title.trim(),
          question: question.trim(),
          text: text.trim() || undefined,
        })
        currentProjectId = created.id
        projectIdRef.current = currentProjectId
        setProjectId(currentProjectId)
      }

      for (let index = uploadedCountRef.current; index < files.length; index += 1) {
        await importProjectMaterial(currentProjectId, files[index])
        uploadedCountRef.current = index + 1
        setUploadedCount(index + 1)
      }

      navigate(`/analyses/${currentProjectId}/modeling`)
      onClose()
    } catch (cause) {
      if (projectIdRef.current) {
        const fileName = files[uploadedCountRef.current]?.name ?? ''
        const reason = cause instanceof ApiError && cause.status === 413
          ? (isZh ? '文件过大。' : 'The file is too large. ')
          : cause instanceof ApiError && cause.status === 415
            ? (isZh ? '暂不支持此文件格式。' : 'This file format is not supported. ')
            : ''
        setError(isZh
          ? `“${fileName}”上传失败。${reason}分析和已上传的材料已保存，可以重试，或先打开分析。`
          : `“${fileName}” could not be uploaded. ${reason}Your analysis and uploaded materials are saved. Retry or open the analysis to continue.`)
      } else {
        setError(isZh ? '暂时无法创建分析，请检查连接后重试。' : 'The analysis could not be created. Check your connection and try again.')
      }
    } finally {
      busyRef.current = false
      setCreating(false)
    }
  }

  const locked = creating || projectId !== null

  return (
    <dialog
      ref={dialogRef}
      className="lu-dialog"
      aria-labelledby={`${id}-title`}
      aria-describedby={`${id}-description`}
      onCancel={(event) => {
        event.preventDefault()
        requestClose()
      }}
    >
      <form className="lu-dialog-form" onSubmit={(event) => void handleSubmit(event)} aria-busy={creating}>
        <header className="lu-dialog-header">
          <div>
            <span className="lu-eyebrow">{isZh ? '新的决策' : 'NEW DECISION'}</span>
            <h2 id={`${id}-title`}>{isZh ? '新建分析' : 'New analysis'}</h2>
            <p id={`${id}-description`}>{isZh ? '描述你要解决的问题，有相关材料也可以一起添加。' : 'Describe the decision you need to make and add any relevant materials.'}</p>
          </div>
          <button type="button" className="lu-icon-button lu-dialog-close" disabled={creating} onClick={requestClose} aria-label={isZh ? '关闭' : 'Close'}>
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg>
          </button>
        </header>

        <div className="lu-dialog-body">
          <label className="lu-field" htmlFor={`${id}-name`}>
            <span>{isZh ? '分析名称' : 'Analysis name'}</span>
            <input id={`${id}-name`} name="title" autoFocus required maxLength={200} disabled={locked} value={title} onChange={(event) => setTitle(event.target.value)} placeholder={isZh ? '例如：第四季度培训计划' : 'e.g. Q4 training plan'} />
          </label>
          <label className="lu-field" htmlFor={`${id}-question`}>
            <span>{isZh ? '决策问题' : 'Decision question'}</span>
            <textarea id={`${id}-question`} name="question" required maxLength={8000} rows={4} disabled={locked} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={isZh ? '你需要决定什么？有哪些目标、限制或时间要求？' : 'What needs to be decided? Include your goals, constraints, and timeframe.'} />
          </label>
          <label className="lu-field" htmlFor={`${id}-text`}>
            <span>{isZh ? '补充说明' : 'Additional context'} <small>{isZh ? '选填' : 'Optional'}</small></span>
            <textarea id={`${id}-text`} name="text" maxLength={20000} rows={3} disabled={locked} value={text} onChange={(event) => setText(event.target.value)} placeholder={isZh ? '粘贴背景信息、业务规则或已有记录' : 'Paste background information, business rules, or existing notes'} />
          </label>

          <div
            className={`lu-upload${dragging ? ' lu-upload-active' : ''}${locked ? ' lu-upload-locked' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              if (!locked) setDragging(true)
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false)
            }}
            onDrop={(event) => {
              event.preventDefault()
              setDragging(false)
              addFiles(Array.from(event.dataTransfer.files))
            }}
          >
            <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="M12 16V3m-4 4 4-4 4 4M5 13v7h14v-7" strokeLinecap="round" strokeLinejoin="round" /></svg>
            <label htmlFor={`${id}-files`} className="lu-upload-label">{isZh ? '添加相关材料' : 'Add supporting materials'} <small>{isZh ? '选填' : 'Optional'}</small></label>
            <p>{isZh ? '拖放文件到这里，或选择文件' : 'Drop files here, or choose files'}</p>
            <input ref={fileInputRef} id={`${id}-files`} className="lu-upload-input" type="file" multiple accept={ACCEPTED_FILES} disabled={locked} onChange={(event) => {
              addFiles(Array.from(event.target.files ?? []))
              event.target.value = ''
            }} />
            <small>{isZh ? '文档、表格、PDF 或图片。不添加文件也可以开始。' : 'Documents, spreadsheets, PDFs, or images. You can also start without files.'}</small>
          </div>

          {files.length > 0 ? (
            <ul className="lu-file-list" aria-label={isZh ? '已选择的文件' : 'Selected files'}>
              {files.map((file, index) => (
                <li key={`${file.name}-${file.size}-${file.lastModified}`}>
                  <span className="lu-file-name">{file.name}</span>
                  <small>{index < uploadedCount ? (isZh ? '已添加' : 'Added') : file.size < 1024 * 1024 ? `${Math.max(1, Math.ceil(file.size / 1024))} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`}</small>
                  {!locked ? <button className="lu-icon-button" type="button" aria-label={isZh ? `移除 ${file.name}` : `Remove ${file.name}`} onClick={() => setFiles((current) => current.filter((_, currentIndex) => currentIndex !== index))}>×</button> : null}
                </li>
              ))}
            </ul>
          ) : null}
          {creating ? <p className="lu-form-status" role="status">{projectId && files.length > 0 ? (isZh ? `正在添加材料 ${uploadedCount + 1} / ${files.length}…` : `Adding material ${uploadedCount + 1} of ${files.length}…`) : (isZh ? '正在创建分析…' : 'Creating analysis…')}</p> : null}
          {error ? <div className="lu-form-error" role="alert"><p>{error}</p>{projectId && !creating ? <Link to={`/analyses/${projectId}/modeling`} onClick={onClose}>{isZh ? '打开已创建的分析' : 'Open the saved analysis'} →</Link> : null}</div> : null}
        </div>

        <footer className="lu-dialog-footer">
          <button className="lu-button lu-button-secondary" type="button" disabled={creating} onClick={requestClose}>{isZh ? '取消' : 'Cancel'}</button>
          <button className="lu-button lu-button-primary" type="submit" disabled={creating || !title.trim() || !question.trim()}>
            {creating ? (isZh ? '处理中…' : 'Working…') : projectId ? (isZh ? '重试上传' : 'Retry upload') : (isZh ? '开始分析' : 'Start analysis')} <span aria-hidden="true">→</span>
          </button>
        </footer>
      </form>
    </dialog>
  )
}
