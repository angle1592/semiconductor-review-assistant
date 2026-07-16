import { Link } from 'react-router-dom'

import { PageHeading } from '../components/Ui'

export function ReviewPage() {
  return (
    <section className="page">
      <PageHeading eyebrow="复习" title="先确认重点，再开始复习" description="复习队列会基于你确认过的重点生成，不会擅自把全部资料变成题目。" />
      <div className="notice-card">
        <span className="index-number">04</span>
        <div>
          <h2>复习队列尚未开放</h2>
          <p>当前版本先完成项目与 AI 接入基础。你可以先创建复习项目，后续导入资料并确认重点。</p>
          <Link className="button button--secondary" to="/projects">查看复习项目</Link>
        </div>
      </div>
    </section>
  )
}
