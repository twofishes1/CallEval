import RuleKGCanvas from "./RuleKGCanvas";
 



export default function ScenePanel({

  scene,

  loading,

  onBuild,

  parsed,

  semanticEdgesAdded,

  kgViz,

}) {

  return (

    <div className="scene-panel">

      <div className="scene-toolbar">

        <button type="button" className="primary" onClick={onBuild} disabled={loading}>

          {loading ? "构建中…" : "构建规则图谱"}

        </button>

        {parsed && (

          <span className="muted">

            流程 {parsed.flow_steps?.length || 0} 步 · 约束{" "}

            {parsed.constraints?.length || 0} 条

            {semanticEdgesAdded != null && (

              <>

                {" "}
                · LLM 语义边 <strong>{semanticEdgesAdded.length}</strong>

              </>

            )}

          </span>

        )}

      </div>



      <div className="kg-only-hint muted">
        仅展示基于解析数据构建的知识图谱（含冲突与修复建议）。图谱结构/冲突由后端生成。
      </div>
      {kgViz && (
        <section className="scene-kg-interactive">
          <RuleKGCanvas kgViz={kgViz} />
        </section>
      )}

 

    </div>

  );

}


