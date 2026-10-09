'use client'
import { useEffect, useMemo, useRef, useState } from 'react'
import { literal, outputValue, parseTable } from './model'
import type { Matrix } from './model'
import styles from './decision-table.module.css'
type Props = {
  value: unknown;
  nodeId?: string;
  readOnly?: boolean;
}
function Grid({ matrix }: {
  matrix: Matrix;
}) {
  const [rowPage, setRowPage] = useState(0)
  const [inputPage, setInputPage] = useState(0)
  const [outputPage, setOutputPage] = useState(0)
  const fields = matrix.fields.slice(inputPage * 12, (inputPage + 1) * 12)
  const outputs = matrix.outputs.slice(outputPage * 12, (outputPage + 1) * 12)
  const rows = matrix.rows.slice(rowPage * 50, (rowPage + 1) * 50)
  const pages = (label: string, current: number, size: number, total: number, set: (n: number) => void) => total > size && <div className={styles.pager}><span>{label} {current * size + 1}–{Math.min((current + 1) * size, total)} / {total}</span><button type="button" aria-label={`${label}上一页`} disabled={current === 0} onClick={() => set(current - 1)}>上一页</button><button type="button" aria-label={`${label}下一页`} disabled={(current + 1) * size >= total} onClick={() => set(current + 1)}>下一页</button></div>
  return <>{(matrix.rows.length > 50 || matrix.fields.length > 12 || matrix.outputs.length > 12) && <div className={styles.pagination}><p>大表分页面板：所有规则和字段均保留，条件编号始终按整条规则计算。</p>{pages('规则', rowPage, 50, matrix.rows.length, setRowPage)}{pages('输入字段', inputPage, 12, matrix.fields.length, setInputPage)}{pages('输出字段', outputPage, 12, matrix.outputs.length, setOutputPage)}</div>}<div className={styles.scroll} tabIndex={0} role="region" aria-label="决策矩阵，可横向滚动">
    <table className={styles.table}>
      <caption className={styles.srOnly}>{matrix.table.id} 决策矩阵，按规则顺序执行</caption>
      <thead><tr><th rowSpan={2} className={styles.ruleHead} scope="col">规则<br /><small>执行顺序 ↓</small></th><th colSpan={Math.max(fields.length, 1)} className={styles.inputGroup} scope="colgroup">输入条件</th><th rowSpan={2} className={styles.logicHead} scope="col">组合逻辑</th><th colSpan={Math.max(outputs.length, 1)} className={styles.outputGroup} scope="colgroup">输出字段</th></tr>
        <tr>{fields.length ? fields.map(f => <th scope="col" className={styles.inputHead} key={f}>{literal(f)}</th>) : <th scope="col" className={styles.inputHead}>无字段条件</th>}{outputs.length ? outputs.map(o => <th scope="col" className={styles.outputHead} key={o.key}>{o.label}</th>) : <th scope="col" className={styles.outputHead}>未定义输出</th>}</tr></thead>
      <tbody>{rows.map((row, i) => <tr key={row.rule.id}>
        <th scope="row" className={styles.rule}><span className={styles.index}>{String(rowPage * 50 + i + 1).padStart(2, '0')}</span><span>{row.rule.id}</span><small className={styles.ruleFormula}>逻辑：{row.logic}</small></th>
        {fields.length ? fields.map(f => <td key={f} className={styles.condition}>{row.atoms.filter(a => a.field === f).map(a => <div key={a.id} className={styles.atom}><b>{a.id}</b><span>{a.label}</span></div>)}{!row.atoms.some(a => a.field === f) && <span className={styles.dash} title="该规则在此字段无独立条件，以组合逻辑为准">—</span>}</td>) : <td className={styles.dash}>—</td>}
        <td className={styles.logic}><strong>{row.logic}</strong>{row.atoms.length > 0 && <details><summary>条件释义</summary><p>{row.fullLogic}</p></details>}</td>
        {outputs.length ? outputs.map((o) => {
          const c = outputValue(row.rule, o)
          let content = <span className={styles.absent}>未提供</span>
          if (c.present)
            content = c.expanded ? <span className={styles.absent}>见字段列</span> : <span className={styles.value}>{literal(c.value!)}</span>

          return <td key={o.key} className={styles.output}>{content}</td>
        }) : <td className={styles.absent}>未提供</td>}
      </tr>)}</tbody>
    </table>
    {!rows.length && <div className={styles.empty}>这张表还没有规则</div>}
  </div></>
}
export default function DecisionTablePreview({ value, nodeId, readOnly = false }: Props) {
  const parsed = useMemo(() => parseTable(value), [value])
  if (parsed.kind !== 'ready')
    return <section className={styles.root} data-node-id={nodeId}><div className={parsed.kind === 'error' ? styles.error : styles.empty}><strong>{parsed.kind === 'error' ? '无法展示决策表' : '决策表'}</strong><p>{parsed.message}</p></div></section>
  return <ReadyPreview key={`${nodeId || ''}:${String(value)}`} matrix={parsed.matrix} nodeId={nodeId} readOnly={readOnly}/>
}
function ReadyPreview({ matrix: m, nodeId, readOnly }: {
  matrix: Matrix;
  nodeId?: string;
  readOnly: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [expanded, setExpanded] = useState(false)
  useEffect(() => {
    if (expanded)
      dialog.current?.showModal()
  }, [expanded])
  const header = <><div><span className={styles.eyebrow}>DECISION TABLE</span><h3>{m.table.id}</h3></div><div className={styles.badges}><span className={styles.policy}>{m.table.hit_policy}</span><span>{m.rows.length} 条规则</span><span>{readOnly ? '只读面板' : '配置预览'}</span></div></>
  return <section className={styles.root} key={nodeId} data-node-id={nodeId}>
    <div className={styles.header}>{header}</div>
    <div className={styles.toolbar}><p>{m.table.hit_policy === 'FIRST' ? '按顺序选择首个成立规则' : '按顺序收集所有成立规则'} · 未知值策略：{m.table.unknown_policy || 'compatible'}{m.table.unknown_policy === 'strict' && '（存在阻塞未知值时会等待）'}</p><button type="button" onClick={() => setExpanded(true)}>展开大表 ↗</button></div>
    <Grid matrix={m}/>
    <div className={styles.legend}><span><b>A / B / C</b> 为本行条件编号</span><span><b>且 / 或</b> 及括号保留原始逻辑</span><span><b>—</b> 此列无独立条件</span></div>
    <p className={styles.note}>展示与执行共用原始 table_json；本视图不修改配置，不计算命中结果。横向滚动可查看全部字段。</p>
    <dialog className={styles.dialog} ref={dialog} onClose={() => setExpanded(false)}>{expanded && <><div className={styles.dialogBar}><div className={styles.header}>{header}</div><button type="button" onClick={() => dialog.current?.close()} autoFocus>关闭大表 ×</button></div><Grid matrix={m}/><p className={styles.note}>条件列中的编号，按“组合逻辑”中的且 / 或关系计算；空白字段不等于默认值。</p></>}</dialog>
  </section>
}
