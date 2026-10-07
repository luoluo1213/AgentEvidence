# AgentEvidence E2E Baseline Human Annotation

Fill `correctness` in the JSON with exactly one of: `correct`, `partial`, `incorrect`.

## single-attention-scaling

Query:
为什么 scaled dot-product attention 要除以 sqrt(d_k)？

Expected concepts:
sqrt(d_k), softmax, dot product, gradient

Answer:
Scaled dot-product attention 除以 √d_k 的原因，是防止 d_k 较大时点积数值过大，从而使 softmax 落入梯度极小的区域。在论文中，注意力计算为 Attention(Q, K, V) = softmax(QK^T/√d_k)V；也就是说，query 与所有 key 计算点积后，先除以 √d_k，再经过 softmax 得到对 value 的权重。论文给出的解释是：当 d_k 较大时，点积的幅度会变大，把 softmax 推到梯度极小的区域；为了抵消这种效应，将点积乘以 1/√d_k。脚注进一步说明了点积为什么会变大：假设 q 和 k 的分量是均值为 0、方差为 1 的独立随机变量，那么 q·k = Σ q_i k_i 的均值为 0、方差为 d_k，所以 d_k 越大，点积的波动幅度越大，除以 √d_k 相当于按其标准差进行缩放。论文还通过比较指出，对较小的 d_k，加法注意力和点积注意力表现相近；但对较大的 d_k，不加缩放的点积注意力不如加法注意力，这也与上述缩放动机一致：无缩放的点积注意力在 d_k 较大时更容易受点积过大和 softmax 小梯度问题影响。

correctness: pending
notes:

## single-attention-position

Query:
Transformer 没有循环和卷积时，怎样表示序列中 token 的顺序？

Expected concepts:
positional encoding, sine, cosine

Answer:
根据所提供证据，无法具体说明 Transformer 如何表示序列中 token 的顺序。证据仅表明：Transformer 是首个完全不使用按序列对齐的 RNN 或卷积、而完全依赖自注意力来计算输入输出表示的转导模型（research:attention_pdf:1555）。相比之下，传统循环模型沿符号位置逐步计算，把位置对齐到计算时间步，用前一隐状态和当前输入生成当前隐状态，因此具有内在顺序性（research:attention_pdf:1548）。但所给材料中没有包含 Transformer 注入或表示 token 顺序的具体机制，例如位置编码的形式或计算方式，因此仅凭这些证据无法回答该问题。

correctness: pending
notes:

## single-attention-heads

Query:
多头注意力如何组合并行 attention heads，base model 使用多少个 heads？

Expected concepts:
MultiHead, Concat, 8

Answer:
多头注意力并不是在 dmodel 维度上只做一次注意力，而是先用不同的、可学习的线性投影把 queries、keys、values 分别投影 h 次，得到每个 head 自己的 QWQ_i、KWK_i、VWV_i。每个 head 并行执行注意力计算，即 headi = Attention(QWQ_i, KWK_i, VWV_i)。随后，所有并行 head 的输出被拼接起来，再通过一个输出投影矩阵 WO 做一次线性投影，公式为 MultiHead(Q, K, V) = Concat(head1, ..., headh)WO，得到最终输出。论文指出，这种机制使模型能够联合关注不同表示子空间、不同位置的信息，而单个 attention head 会因为平均而抑制这一点。对于 Transformer base model，论文采用 h = 8 个并行 attention heads，每个 head 的维度为 dk = dv = dmodel/h = 64；由于每个 head 的维度降低，总计算成本与全维度的单头注意力相近。

correctness: pending
notes:

## single-react-interleave

Query:
ReAct 如何交错进行推理和行动，环境反馈起什么作用？

Expected concepts:
thought, action, observation, interleave

Answer:
ReAct 的交错方式体现在：它不把推理局限于孤立、固定的思维链，而是将智能体动作空间扩展为 A∪L，其中 L 是语言空间，使模型能在动作之间生成语言推理轨迹。具体地，ReAct 提示大语言模型以交错方式生成与任务相关的言语推理轨迹和动作：一方面通过动态推理建立、维持和调整高层行动计划（reason to act），另一方面与外部环境（如 Wikipedia）交互，从而把外部信息纳入推理（act to reason）。

环境反馈的作用是作为行动后的观察被整合进模型的连贯输入流。模型要依据 Question、Act、Obs 构成的轨迹上下文进行复杂推理；观察为后续推理提供额外信息，使推理更准确，并使模型能处理超出纯推理的交互式决策任务。如果模型未能正确理解观察，例如没有认识到 sinkbasin 1 不包含 peppershaker 1，就会不断产生幻觉性动作。

结果层面，ReAct 在 HotpotQA 和 Fever 上以 PaLM-540B 为基础模型一致优于 Act，说明推理对行动有指导价值，尤其体现在综合最终答案上。需要补充的是，交错推理轨迹并非自动可信：某条轨迹曾因幻觉性思考失败，人工仅编辑两个思考后即可得到合适的推理和动作并成功；这种干预在 Act 和以往 RL 方法中较难实现。

correctness: pending
notes:

## single-react-trajectory

Query:
ReAct 的 trajectory 中，哪些元素由模型生成，哪些来自环境？

Expected concepts:
Thought, Act, Obs

Answer:
在 ReAct 的 trajectory 中，基本步骤由 thought、action、observation 三类元素构成。其中，thought 和 action 由语言模型生成：ReAct 提示 LLM 以交错方式生成言语推理轨迹和动作，并由模型自己决定 thought 与 action 何时出现；thought 还可能是模型幻觉产生的。observation 不是模型生成的，而是模型动作所对应的反馈，这些信息来自与外部环境（如 Wikipedia、真实网页）的交互，随后作为输入被整合回模型的上下文，用于继续推理。因此，模型生成的是 thought 与 action，来自环境的是 observation。

correctness: pending
notes:

## single-react-grounding

Query:
ReAct 在问答任务中如何通过外部信息减少幻觉？

Expected concepts:
Wikipedia, hallucination, grounding

Answer:
在问答任务中，ReAct 主要通过“与外部环境交互并获取观察信息”来减少语言模型幻觉。具体而言，在 HotpotQA 问答和 FEVER 事实验证上，ReAct 通过调用简单的 Wikipedia API 获取外部信息，从而克服了链式思维推理中普遍存在的幻觉和错误传播问题。其机制是：ReAct 促使语言模型以交错方式同时生成语言推理轨迹和任务动作；模型不仅可以通过推理来规划行动，还可以通过执行动作与外部环境交互，把额外信息纳入后续推理。这样，模型不再只依赖参数内部的先验知识作答，而是利用 Wikipedia 返回的观察作为证据来辅助推理，降低编造答案的风险。同时，ReAct 将动作空间扩展为 A∪L，加入语言思维空间 L，使模型能够在行动前和行动间进行显式推理，并根据“Question、Act、Obs”组成的轨迹上下文进行复杂推理，避免因未理解上下文而持续产生幻觉式动作。

correctness: pending
notes:

## single-reflexion-verbal-memory

Query:
Reflexion 如何利用语言反馈和情景记忆，在多次 trial 之间改进行为？

Expected concepts:
verbal, episodic memory, trial, self-reflection

Answer:
Reflexion 通过语言反馈和情景记忆在多 trial 之间改进行为，而不是通过更新模型权重。其语言反馈生成过程是：Actor 先与环境交互产生轨迹，Evaluator 给出标量或二元奖励；随后 Self-Reflection 模型分析轨迹与奖励，将奖励放大为语言化的经验反馈摘要 srt。该框架可接受标量值或自由形式语言，并可纳入外部或内部模拟的反馈信号。在编程任务示例中，Self-Reflection 的生成格式包括指令、函数实现和单元测试反馈，Actor 生成则在此基础上加入自我反思和下一条函数实现指令。情景记忆的存储与利用表现为：每次 trial 后 srt 被追加到记忆 mem，并用容量上限 Ω（通常 1-3）或截断到最近 3 次自我反思来控制上下文长度。推理时，Actor 同时条件于短期轨迹历史和长期自我反思输出，使后续 trial 获得既包含具体细节又包含跨 trial 教训的上下文。多 trial 循环中，Actor、Evaluator、Self-Reflection 持续工作，直到 Evaluator 判定轨迹正确；代理通过自我反思发现错误、更新记忆、重置环境并开始新 trial，下一 episode 将语言反馈作为额外上下文。这一 trial、错误、自我反思、持久化记忆的迭代过程使行为逐步改进；证据显示其在 HumanEval 达到 91% pass@1，并在 HotPotQA 上改善搜索、信息检索和推理。

correctness: pending
notes:

## single-reflexion-memory-types

Query:
Reflexion 的短期记忆和长期记忆分别保存什么？

Expected concepts:
trajectory, short-term, long-term, reflection

Answer:
在 Reflexion 中，短期记忆和长期记忆保存的内容不同。短期记忆保存的是轨迹历史（trajectory history），即 Actor 与环境交互产生的轨迹；长期记忆保存的是 Self-Reflection 模型生成的言语化自我反思（verbal self-reflections），这些反思文本被写入持久记忆或情景记忆缓冲区，并在后续试验中提供从多个 trial 中学到的经验教训。二者共同为 Actor 提供决策上下文：短期记忆提供细粒度的近期细节，长期记忆提供多轮学习得到的提炼经验。论文还说明，当前实现中长期记忆被限制为具有最大容量的滑动窗口。

correctness: pending
notes:

## single-reflexion-three-models

Query:
Reflexion 中 Actor、Evaluator 和 Self-Reflection 如何跨 trial 协作？

Expected concepts:
Actor, Evaluator, Self-Reflection, memory

Answer:
在 Reflexion 中，Actor、Evaluator 和 Self-Reflection 通过持久记忆 mem 串联为跨 trial 的迭代优化循环。初始化时先设置 Actor（Ma）、Evaluator（Me）与 Self-Reflection（Msr），并将策略参数 θ 设为 {Ma, mem}。首个 trial 由 Actor 与环境交互生成轨迹 τ0；Evaluator 对 τ0 计算标量奖励 r0=Me(τ0)；随后 Self-Reflection 分析集合 {τ0, r0}，生成言语经验反馈 sr0，并将 mem 初始化为 [sr0]。之后的 trial 按 Algorithm 1 的 while 条件（Me not pass or t < max trials）循环执行：Actor 生成新轨迹 τt，Evaluator 给出 rt，Self-Reflection 生成 srt 并把 srt 追加到 mem；循环在 Evaluator 判定 τt 正确时结束。Self-Reflection 的独特作用是把 Evaluator 返回的稀疏标量信号（如成功/失败）、当前轨迹与持久记忆 mem 结合，生成比标量奖励更具信息量的细致反馈；这些言语反馈被保存在 mem 中，Actor 在后续推理时条件化地利用短期轨迹和长期经验进行决策。为避免超出上下文，mem 通常仅保留最近 Ω=1–3 条经验。代码生成任务的模板也显示，Actor 的生成形式包含上一轮 Self-reflection 与下一函数实现指令。整体上，trial、error、self-reflection 与 persisting memory 的迭代使 Reflexion 智能体利用信息性反馈快速改进决策。

correctness: pending
notes:

## compare-react-reflexion-feedback

Query:
比较 ReAct 和 Reflexion 在利用反馈改进智能体行为方面的主要差异。

Expected concepts:
observation, verbal reflection, trial

Answer:
无法基于当前证据可靠生成回答

correctness: pending
notes:

## compare-react-reflexion-memory

Query:
比较 ReAct 的 trajectory 与 Reflexion 的情景记忆：各保存什么，又在什么时间尺度上被复用？

Expected concepts:
trajectory, episodic memory, episode

Answer:
ReAct 的 trajectory 保存的是当前任务交互中由语言模型生成的思考与动作序列：thoughts 可以异步出现在轨迹中最相关的位置，轨迹把推理文本与环境动作交织在一起。证据显示它主要在单次 trajectory 的时间尺度上被检查、编辑和继续使用，例如人类编辑轨迹中的两个 thought 后，同一轨迹即可转向正确的推理痕迹和动作；轨迹检查也用于发现模型判断与数据标签不一致。ReAct-IM 的轨迹还常因缺少高层目标分解和常识推理而在判断子目标或定位物品时出错，这些缺点可在 ReAct 范式中处理。从提供的证据看，ReAct 论文对 trajectory 的讨论集中在单次任务轨迹内部，而不是将其描述为跨 trial 累积的长期记忆。

Reflexion 的情景记忆保存的是智能体对任务反馈信号进行口头反思后生成的自我反思文本，并维护在 episodic memory buffer 中；反馈类型可以是标量或自由语言，来源可以是外部或内部模拟。时间尺度上，Reflexion 把 trajectory history 作为短期记忆，把 Self-Reflection 模型的输出存入长期记忆，在后续 trial 中复用，并提供受多个 trial 经验影响的上下文；长期记忆在实现上被限制为有最大容量的滑动窗口。消融实验也对比了 Reflexion 与去除情景记忆的版本，以分离自我反思步骤的作用。

关键差异是：ReAct trajectory 保存的是原始 thought/action 轨迹，属于单次任务内的 trace；Reflexion episodic memory 保存的是从反馈中提炼出的反思文本，跨多个后续 trial 复用。ReAct 轨迹复用的时间尺度是当前 episode 内，表现为轨迹检查与少量 thought 编辑；Reflexion 情景记忆复用的时间尺度是跨 trial 的长期滑动窗口。两者都利用自然语言形式的轨迹或记忆为后续决策提供上下文，但 Reflexion 在此基础上增加了跨 trial 的提炼、长期存储与容量限制。

correctness: pending
notes:

## compare-react-reflexion-trials

Query:
ReAct 和 Reflexion 在跨 trial 使用反馈、而不是只在单条 trajectory 内使用反馈上有何不同？

Expected concepts:
within-trajectory, across trials, reflection

Answer:
ReAct 的反馈利用主要发生在单条 trajectory 内部。它将推理与行动集成到同一个语言模型中，由语言模型自己决定 Thought 和 Action 的异步出现；在 AlfWorld 的人类介入示例中，失败轨迹源于一个幻觉 Thought，人类只编辑两个 Thought 就能让同一条轨迹的后续推理和行动变得合理并成功，说明纠偏作用于灵活的 thought 空间，而不是改模型参数或只改个别动作。ReAct 对 IM 式密集外部反馈的消融还显示，ReAct 显著优于 ReAct-IM，表明其核心不是简单回应外部反馈，而是内部推理。

Reflexion 则显式地跨 trial 使用反馈。它不更新权重，而是通过语言反馈强化代理：代理对任务反馈进行言语反思，并将反思文本保持在 episodic memory buffer 中，用于后续 trial 的决策改进。具体来说，Actor 生成 trajectory τ0，Evaluator 给出标量 reward r0，Self-Reflection 分析 {τ0, r0} 生成 verbal experience feedback sr0 存入 memory；之后每个 trial 的 srt 都被追加到 mem，mem 以 Ω 限制，通常只保留 1–3 条经验。在 AlfWorld 的对照中，不使用 self-reflection 的 baseline 只是重置环境并开始新 trial；Reflexion 则会通过 self-reflection 找到错误、更新 memory、再重置环境，并将记忆截断为最近 3 条 self-reflection。

关键区别在于反馈使用范围、记忆机制和跨 trial 改进方式。ReAct 的反馈或纠偏主要发生在单条轨迹的 thought 空间中，所提供的 ReAct 证据没有 Reflexion 那种跨 trial 的 episodic memory buffer 来累积、裁剪并复用 verbal feedback。Reflexion 的反馈以 scalar reward 为起点，经 Self-Reflection 放大为语言化的 srt 并纳入跨 trial memory；ReAct 则把观察与内部 thought 交织在当前轨迹中调整后续行动。跨 trial 数据也显示：在 AlfWorld 中，ReAct-only 的性能增益在 trial 6 到 7 之间停滞，而 ReAct + Reflexion 在连续 12 个 trial 中继续学习解决更多任务。但 Reflexion 的跨 trial feedback 并非在所有任务上都带来显著收益：在 WebShop 上 ReAct + Reflexion 未能显著超过 ReAct。

correctness: pending
notes:

## compare-react-reflexion-feedback-timing

Query:
比较 ReAct 与 Reflexion：环境或 evaluator 反馈分别在什么时候进入下一步决策？

Expected concepts:
observation, next episode, evaluator

Answer:
ReAct 与 Reflexion 在反馈进入下一步决策的时机和机制上明显不同。ReAct 在单个交互轨迹内部使用环境反馈：模型以交错方式生成推理轨迹和动作，动作执行后环境返回观察，这些观察与动作一起被整合为连贯输入流，供模型进行后续推理和决策。因此，ReAct 的环境反馈是在同一轨迹内、动作执行之后立即以文本观察的形式进入下一步推理，例如 Wikipedia 搜索返回的信息。Reflexion 则在试验层面使用评估反馈：Actor 先与环境交互生成轨迹 τ0，Evaluator 再基于该轨迹给出标量分数 r0；随后 Self-Reflection 模型分析轨迹和分数，将标量奖励放大为可用于 LLM 改进的言语经验反馈，并写入记忆。在后续 trial 中，轨迹历史作为短期记忆、Self-Reflection 输出作为长期记忆，共同为 Actor 提供额外上下文。因此，Reflexion 的 evaluator 反馈不是即时进入同一轨迹的下一步，而是在 trial 结束后被转化为言语反馈，通过 memory 影响后续试验。总体差异是：ReAct 是轨迹内、动作级、环境观察即时回流；Reflexion 是轨迹间、试验级、标量评估经自我反思转成言语记忆后延迟回流。ReAct 单独运行时可能陷入重复思考和动作的推理错误，而 Reflexion 的跨试验记忆和反思机制用于在后续 trial 中改进决策。

correctness: pending
notes:

## session-react-feedback

Query:
它的环境反馈具体起什么作用？

Expected concepts:
observation, reason, act

Answer:
在 ReAct 框架中，环境反馈/观察不是孤立提供答案，而是进入推理与行动的闭环。具体而言：第一，它是“act to reason”的外部信息来源，ReAct 让模型与外部环境（如 Wikipedia）交互，把环境返回的额外信息纳入后续推理。第二，环境观察与模型动作被整合为前后连贯的输入流，模型基于这个动作—观察轨迹进行更准确的推理，从而处理交互式决策任务，而不只是进行孤立、固定的推理。第三，环境反馈/检索质量直接影响循环能否成功：通过搜索成功检索到有信息量的知识对 ReAct 至关重要，否则模型可能重复先前产生的想法和动作、无法推理出下一步并跳出循环。进一步看，环境反馈并不替代推理，而是与推理轨迹配合：ReAct 在 HotpotQA 和 Fever 上持续优于仅行动方法，说明在环境交互基础上加入推理轨迹有助于合成最终答案并做出更明智行动。在闭环系统层面，ReAct 是 LLM 在交互环境中结合推理与行动的首次演示；但现有方法仍远不及专家人类，专家人类会进行显著更多的产品探索和查询重写，而这些对提示式方法仍具挑战性，说明对环境的充分探索和反馈利用仍有限。

correctness: pending
notes:

## session-reflexion-long-term

Query:
长期记忆里存的是什么？

Expected concepts:
self-reflection, long-term

Answer:
Reflexion 的长期记忆（情景记忆缓冲区）中存储的是智能体自己的反思文本，具体来说是 Self-Reflection 模型输出的反思内容。与之相对，轨迹历史充当短期记忆；长期记忆保存这些反思输出，并在后续推理时与短期记忆一起为 Actor 提供上下文，使决策既包含近期细节，也包含从多次 trial 中提炼的经验。实现上，本研究将长期记忆限制为一个具有最大容量的滑动窗口，而不是无界存储。

correctness: pending
notes:

## cross-session-attention-scaling

Query:
继续之前的主题：它为什么要除以 sqrt(d_k)？

Expected concepts:
softmax, dot product

Answer:
Scaled Dot-Product Attention 在计算 query 与所有 key 的点积后，先把每个点积除以 √d_k，再经过 softmax 得到各个 value 的权重。论文给出的原因是：当 d_k 较大时，点积的数值规模会变大，softmax 会被推到梯度极小的区域，导致学习变得困难；因此在 softmax 之前使用 1/√d_k 进行缩放，以抵消这种效应。其背后的机制是：如果 q 和 k 的各个分量是均值为 0、方差为 1 的独立随机变量，那么 q·k = Σ q_i k_i 的均值为 0、方差为 d_k，所以用 √d_k 来缩放可以控制点积的尺度。公式上体现为 Attention(Q, K, V) = softmax(QK^T/√d_k)V。作为对照，对于较小的 d_k，additive attention 与 dot-product attention 表现相近；但在 d_k 较大时，additive attention 优于不带缩放的 dot-product attention。

correctness: pending
notes:

## cross-session-reflexion-next-trial

Query:
继续我们之前的分析：它如何把失败变成下一 trial 可用的信息？

Expected concepts:
verbal, memory, trial

Answer:
在 Reflexion 框架中，失败不是被直接丢弃：每个 trial 后 Evaluator 给出标量奖励 rt（如二元成功/失败），第一 trial 形成轨迹 τ0 和奖励 r0；Self-Reflection 模型以稀疏奖励、当前轨迹和持久记忆 mem 为输入，把 {τ0, r0} 放大为比标量奖励更具信息量的自然语言经验总结 sr0，并写入 mem。失败时，它能定位导致后续错误的具体动作 ai，提出本应采取的替代动作 a′i 及其后续结果；下一 trial 的 Actor 在推理时依据短期和长期记忆作决策，因此可在时间步 t 改用 a′i。循环执行时，Reflexion 用 self-reflection 找出错误、更新记忆、重置环境，再开始新 trial；记忆截断为最近 3 条自我反思经验以控制提示长度。总体机制就是把评估信号放大为自然语言经验摘要，存储到长期记忆，供后续 trial 使用。

correctness: pending
notes:
