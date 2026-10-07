# AgentEvidence E2E Baseline Human Annotation

Fill `correctness` in the JSON with exactly one of: `correct`, `partial`, `incorrect`.

## compare-react-reflexion-feedback

Query:
比较 ReAct 和 Reflexion 在利用反馈改进智能体行为方面的主要差异。

Expected concepts:
observation, verbal reflection, trial

Answer:
ReAct 的反馈利用机制集中在单次交互轨迹内部：它把模型动作与对应观察整合为一个连贯输入流，使模型能够更准确地推理，并处理交互式决策任务；其优势来自内部推理，而不是简单地对密集外部反馈作出反应。Reflexion 则引入跨试验的反馈利用：智能体在获得任务反馈后，用自然语言对反馈信号进行言语化反思，并把反思文本保存在情景记忆缓冲区中，在后续试验中诱导更好的决策；反馈既可以是标量也可以是自由语言，来源既可以是外部也可以是内部模拟。主要差异表现为：第一，时间尺度不同，ReAct 在单次轨迹内利用动作-观察流和内部推理，Reflexion 在多次试验之间利用反思记忆；第二，反馈处理不同，ReAct 将观察纳入连贯推理流，Reflexion 将反馈转化为可存储的反思文本；第三，错误修正能力不同，Reflexion 能检测幻觉和低效规划，并通过后续试验改进，而 ReAct-only 在 ALFWorld 中常见无法回溯定位的错误，且性能提升会停滞。经验比较中，ReAct+Reflexion 在 ALFWorld 显著优于 ReAct（134 个任务完成 130 个），在 HotPotQA 上 Reflexion 改善了搜索、信息检索和推理能力；但在 WebShop 上 ReAct+Reflexion 未能显著优于 ReAct，说明反馈增益具有任务依赖性。

correctness: pending
notes:
