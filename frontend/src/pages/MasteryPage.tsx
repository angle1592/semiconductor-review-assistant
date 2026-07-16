import { PageHeading } from '../components/Ui'

export function MasteryPage() {
  return (
    <section className="page">
      <PageHeading eyebrow="掌握情况" title="掌握记录会从每次复习中累积" description="这里将按项目展示薄弱点、复习次数和最近变化。" />
      <div className="notice-card">
        <span className="index-number">05</span>
        <div>
          <h2>还没有掌握记录</h2>
          <p>完成第一轮重点复习后，这里才会出现真实数据。</p>
        </div>
      </div>
    </section>
  )
}
