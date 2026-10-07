# AgentEvidence E2E Human Annotation

Status: **PENDING HUMAN REVIEW**

## Case: single-attention-scaling

Query:
在 scaled dot-product attention 中，softmax 前如何缩放 query-key 点积？为什么？

Reference Answer Points:
- 点积除以 √dk 后再做 softmax
- 缩放用于缓解大 dk 下点积增大并使 softmax 梯度极小的问题

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

Scaled Dot-Product Attention
Multi-Head Attention
Figure 2: (left) Scaled Dot-Product Attention. (right) Multi-Head Attention consists of several
attention layers running in parallel. of the values, where the weight assigned to each value is computed by a compatibility function of the
query with the corresponding key. 3.2.1 Scaled Dot-Product Attention
We call our particular attention "Scaled Dot-Product Attention" (Figure 2).

## Page 4

The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values. In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V .
2. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

We compute
the matrix of outputs as:
Attention(Q, K, V) = softmax(QKT
√dk
)V (1)
The two most commonly used attention functions are additive attention [2], and dot-product (multi-
plicative) attention. Dot-product attention is identical to our algorithm, except for the scaling factor
of 1√dk
. Additive attention computes the compatibility function using a feed-forward network with
a single hidden layer.
3. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values. In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V .
4. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

We suspect that for large values of
dk, the dot products grow large in magnitude, pushing the softmax function into regions where it has
extremely small gradients 4. To counteract this effect, we scale the dot products by 1√dk
.
5. [research:attention_pdf / page 5 / Page 5]
   ## Page 5

We need to prevent leftward
information flow in the decoder to preserve the auto-regressive property. We implement this
inside of scaled dot-product attention by masking out (setting to −∞) all values in the input
of the softmax which correspond to illegal connections. See Figure 2.
6. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

While the two are similar in theoretical complexity, dot-product attention is
much faster and more space-efficient in practice, since it can be implemented using highly optimized
matrix multiplication code. While for small values of dk the two mechanisms perform similarly, additive attention outperforms
dot product attention without scaling for larger values of dk [3].
7. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

On each of these projected versions of
queries, keys and values we then perform the attention function in parallel, yielding dv-dimensional
4To illustrate why the dot products get large, assume that the components of q and k are independent random
variables with mean 0 and variance 1. Then their dot product, q · k = Pdk
i=1 qiki, has mean 0 and variance dk.
8. [research:attention_pdf / page 3 / Page 3]
   ## Page 3

We also modify the self-attention
sub-layer in the decoder stack to prevent positions from attending to subsequent positions. This
masking, combined with fact that the output embeddings are offset by one position, ensures that the
predictions for position i can depend only on the known outputs at positions less than i. 3.2 Attention
An attention function can be described as mapping a query and a set of key-value pairs to an output,
where the query, keys, values, and output are all vectors.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-attention-position

Query:
Transformer 没有循环和卷积时，怎样表示序列中 token 的顺序？

Reference Answer Points:
- 在 encoder 和 decoder 底部给输入 embedding 加入 positional encoding
- 论文使用不同频率的正弦和余弦函数

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:attention_pdf / page 5 / Page 5]
   ## Page 5

3.3 Position-wise Feed-Forward Networks
In addition to attention sub-layers, each of the layers in our encoder and decoder contains a fully
connected feed-forward network, which is applied to each position separately and identically. This
consists of two linear transformations with a ReLU activation in between. FFN(x) = max(0, xW1 + b1)W2 + b2 (2)
While the linear transformations are the same across different positions, they use different parameters
from layer to layer.

## Page 5

Another way of describing this is as two convolutions with kernel size 1. The dimensionality of input and output is dmodel = 512, and the inner-layer has dimensionality
dff = 2048. 3.4 Embeddings and Softmax
Similarly to other sequence transduction models, we use learned embeddings to convert the input
tokens and output tokens to vectors of dimension dmodel. We also use the usual learned linear transfor-
mation and softmax function to convert the decoder output to predicted next-token probabilities.

## Page 5

In
our model, we share the same weight matrix between the two embedding layers and the pre-softmax
linear transformation, similar to [30]. In the embedding layers, we multiply those weights by √dmodel.
2. [research:attention_pdf / page 3 / Page 3]
   ## Page 3

Figure 1: The Transformer - model architecture. The Transformer follows this overall architecture using stacked self-attention and point-wise, fully
connected layers for both the encoder and decoder, shown in the left and right halves of Figure 1,
respectively. 3.1 Encoder and Decoder Stacks
Encoder: The encoder is composed of a stack of N = 6 identical layers. Each layer has two
sub-layers.
3. [research:attention_pdf / page 2 / Page 2]
   ## Page 2

Recurrent models typically factor computation along the symbol positions of the input and output
sequences. Aligning the positions to steps in computation time, they generate a sequence of hidden
states ht, as a function of the previous hidden state ht−1 and the input for position t. This inherently
sequential nature precludes parallelization within training examples, which becomes critical at longer
sequence lengths, as memory constraints limit batching across examples.
4. [research:attention_pdf / page 2 / Page 2]
   ## Page 2

To the best of our knowledge, however, the Transformer is the first transduction model relying
entirely on self-attention to compute representations of its input and output without using sequence-
aligned RNNs or convolution. In the following sections, we will describe the Transformer, motivate
self-attention and discuss its advantages over models such as [17, 18] and [9]. 3 Model Architecture
Most competitive neural sequence transduction models have an encoder-decoder structure [5, 2, 35].
5. [research:attention_pdf / page 2 / Page 2]
   ## Page 2

In this work we propose the Transformer, a model architecture eschewing recurrence and instead
relying entirely on an attention mechanism to draw global dependencies between input and output. The Transformer allows for significantly more parallelization and can reach a new state of the art in
translation quality after being trained for as little as twelve hours on eight P100 GPUs.
6. [research:attention_pdf / page 9 / Page 9]
   ## Page 9

Table 3: Variations on the Transformer architecture. Unlisted values are identical to those of the base
model. All metrics are on the English-to-German translation development set, newstest2013. Listed
perplexities are per-wordpiece, according to our byte-pair encoding, and should not be compared to
per-word perplexities.
7. [research:attention_pdf / page 10 / Page 10]
   ## Page 10

7 Conclusion
In this work, we presented the Transformer, the first sequence transduction model based entirely on
attention, replacing the recurrent layers most commonly used in encoder-decoder architectures with
multi-headed self-attention. For translation tasks, the Transformer can be trained significantly faster than architectures based
on recurrent or convolutional layers. On both WMT 2014 English-to-German and WMT 2014
English-to-French translation tasks, we achieve a new state of the art.
8. [research:attention_pdf / page 8 / Page 8]
   ## Page 8

6 Results
6.1 Machine Translation
On the WMT 2014 English-to-German translation task, the big transformer model (Transformer (big)
in Table 2) outperforms the best previously reported models (including ensembles) by more than 2.0
BLEU, establishing a new state-of-the-art BLEU score of 28.4. The configuration of this model is
listed in the bottom line of Table 3. Training took 3.5 days on 8 P100 GPUs.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-attention-heads

Query:
多头注意力如何组合并行 attention heads，base model 使用多少个 heads？

Reference Answer Points:
- 各 head 输出先拼接再经过输出投影矩阵
- base model 使用 8 个并行 attention heads

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:attention_pdf / page 5 / Page 5]
   ## Page 5

output values. These are concatenated and once again projected, resulting in the final values, as
depicted in Figure 2. Multi-head attention allows the model to jointly attend to information from different representation
subspaces at different positions. With a single attention head, averaging inhibits this.

## Page 5

MultiHead(Q, K, V) = Concat(head1, ...,headh)WO
where headi = Attention(QWQ
i , KWK
i , V WV
i )
Where the projections are parameter matricesWQ
i ∈ Rdmodel×dk , WK
i ∈ Rdmodel×dk , WV
i ∈ Rdmodel×dv
and WO ∈ Rhdv×dmodel . In this work we employ h = 8 parallel attention layers, or heads. For each of these we use
dk = dv = dmodel/h = 64. Due to the reduced dimension of each head, the total computational cost
is similar to that of single-head attention with full dimensionality.

## Page 5

3.2.3 Applications of Attention in our Model
The Transformer uses multi-head attention in three different ways:
• In "encoder-decoder attention" layers, the queries come from the previous decoder layer,
and the memory keys and values come from the output of the encoder. This allows every
position in the decoder to attend over all positions in the input sequence. This mimics the
typical encoder-decoder attention mechanisms in sequence-to-sequence models such as
[38, 2, 9].
2. [research:attention_pdf / page 9 / Page 9]
   ## Page 9

We used beam search as described in the previous section, but no
checkpoint averaging. We present these results in Table 3. In Table 3 rows (A), we vary the number of attention heads and the attention key and value dimensions,
keeping the amount of computation constant, as described in Section 3.2.2. While single-head
attention is 0.9 BLEU worse than the best setting, quality also drops off with too many heads. In Table 3 rows (B), we observe that reducing the attention key size dk hurts model quality.
3. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

3.2.2 Multi-Head Attention
Instead of performing a single attention function with dmodel-dimensional keys, values and queries,
we found it beneficial to linearly project the queries, keys and values h times with different, learned
linear projections to dk, dk and dv dimensions, respectively.
4. [research:attention_pdf / page 5 / Page 5]
   ## Page 5

output values. These are concatenated and once again projected, resulting in the final values, as
depicted in Figure 2. Multi-head attention allows the model to jointly attend to information from different representation
subspaces at different positions. With a single attention head, averaging inhibits this.
5. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

Scaled Dot-Product Attention
Multi-Head Attention
Figure 2: (left) Scaled Dot-Product Attention. (right) Multi-Head Attention consists of several
attention layers running in parallel. of the values, where the weight assigned to each value is computed by a compatibility function of the
query with the corresponding key. 3.2.1 Scaled Dot-Product Attention
We call our particular attention "Scaled Dot-Product Attention" (Figure 2).
6. [research:attention_pdf / page 15 / Page 15]
   ## Page 15

<EOS>
<pad>
The
Law
will
never
be
perfect
,
but
its
application
should
be
just
-
this
is
what
we
are
missing
,
in
my
opinion
. <EOS>
<pad>
Figure 5: Many of the attention heads exhibit behaviour that seems related to the structure of the
sentence. We give two such examples above, from two different heads from the encoder self-attention
at layer 5 of 6. The heads clearly learned to perform different tasks.
7. [research:attention_pdf / page 7 / Page 7]
   ## Page 7

We inspect attention distributions
from our models and present and discuss examples in the appendix. Not only do individual attention
heads clearly learn to perform different tasks, many appear to exhibit behavior related to the syntactic
and semantic structure of the sentences. 5 Training
This section describes the training regime for our models. 5.1 Training Data and Batching
We trained on the standard WMT 2014 English-German dataset consisting of about 4.5 million
sentence pairs.
8. [research:attention_pdf / page 13 / Page 13]
   ## Page 13

<EOS>
<pad>
<pad>
<pad>
<pad>
<pad>
<pad>
Figure 3: An example of the attention mechanism following long-distance dependencies in the
encoder self-attention in layer 5 of 6. Many of the attention heads attend to a distant dependency of
the verb ‘making’, completing the phrase ‘making...more difficult’. Attentions here shown only for
the word ‘making’. Different colors represent different heads. Best viewed in color.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-react-loop

Query:
ReAct 的 reason-to-act 与 act-to-reason 循环如何工作？

Reference Answer Points:
- 推理轨迹帮助形成、跟踪和更新行动计划
- 行动与外部环境交互并获得信息，信息再进入后续推理
- 推理与行动交错生成

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 2 / Page 2]
   ## Page 2

Beyond such simple embodied tasks to interact with a few blocks, there have not been
studies on how reasoning and acting can be combined in a synergistic manner for general task solving,
and if such a combination can bring systematic beneﬁts compared to reasoning or acting alone. In this work, we present ReAct, a general paradigm to combine reasoning and acting with language
models for solving diverse language reasoning and decision making tasks (Figure 1).

## Page 2

ReAct
prompts LLMs to generate both verbal reasoning traces and actions pertaining to a task in an
interleaved manner, which allows the model to perform dynamic reasoning to create, maintain, and
adjust high-level plans for acting (reason to act), while also interact with the external environments
(e.g. Wikipedia) to incorporate additional information into reasoning (act to reason).
2. [research:react_pdf / page 9 / Page 9]
   ## Page 9

In contrast to these methods, ReAct performs more than just isolated, ﬁxed reasoning, and integrates
model actions and their corresponding observations into a coherent stream of inputs for the model to
reason more accurately and tackle tasks beyond reasoning (e.g. interactive decision making).
3. [research:react_pdf / page 6 / Page 6]
   ## Page 6

In contrast,
ﬁnetuning Standard or CoT is signiﬁcantly worse than ﬁnetuning ReAct or Act for both PaLM-
8/62B, as the former essentially teaches models to memorize (potentially halluincated) knowledge
facts, and the latter teaches models how to (reason and) act to access information from Wikipedia, a
more generalizable skill for knowledge reasoning.
4. [research:react_pdf / page 6 / Page 6]
   ## Page 6

we note that there is one frequent
error pattern speciﬁc to ReAct, in which the model repetitively generates the previous thoughts and
actions, and we categorize it as part of “reasoning error” as the model fails to reason about what the
proper next action to take and jump out of the loop4. C) For ReAct, successfully retrieving informative knowledge via search is critical.
5. [research:react_pdf / page 15 / Page 15]
   ## Page 15

(a) ReAct
trajectory fails due to a hallucinating thought (Act 17). (b) By a human simply editing two thoughts
(Act 17, 23), the ReAct trajectory produces desirable reasoning traces and actions and succeeds. is difﬁcult for Act and previous RL methods, as a human cannot change the model parameters, and
changing a few actions might not edit the rest of the model behavior. This paradigm is also more than
human dialogue to update the goal or subgoal as in Huang et al.
6. [research:react_pdf / page 4 / Page 4]
   ## Page 4

appear sparsely in the most relevant positions of a trajectory, so we let the language model decide the
asynchronous occurrence of thoughts and actions for itself. Since decision making and reasoning capabilities are integrated into a large language model, ReAct
enjoys several unique features: A) Intuitive and easy to design : Designing ReAct prompts is
straightforward as human annotators just type down their thoughts in language on top of their actions
taken.
7. [research:react_pdf / page 8 / Page 8]
   ## Page 8

Qualitatively, we saw that, without any thoughts at all, Act fails to correctly decompose goals
into smaller subgoals, or loses track of the current state of the environment. Example trajectories
comparing ReAct and Act can be found in Appendix D.2.1 and Appendix D.2.2. On Webshop, one-shot Act prompting already performs on par with IL and IL+RL methods. With
additional sparse reasoning, ReAct achieves signiﬁcantly better performance, with an absolute 10%
improvement over the previous best success rate.
8. [research:react_pdf / page 8 / Page 8]
   ## Page 8

Perhaps the closest prior work is Inner Monologue (IM), from Huang
et al. (2022b), in which actions from an embodied agent are motivated by an eponymous “inner
monologue”. However, IM’s “inner monologue” is limited to observations of the environment
state and what needs to be completed by the agent for the goal to be satisﬁed. In contrast, the
reasoning traces in ReAct for decision making is ﬂexible and sparse, allowing diverse reasoning
types (see Section 2) to be induced for different tasks.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-react-trajectory

Query:
ReAct trajectory 中哪些元素由模型生成，哪些来自环境？

Reference Answer Points:
- Thought 和 Act 由模型生成
- Observation 由环境返回

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 8 / Page 8]
   ## Page 8

Qualitatively, we observed that ReAct-IM often made mistakes
in identifying when subgoals were ﬁnished, or what the next subgoal should be, due to a lack of high-
level goal decomposition. Additionally, many ReAct-IM trajectories struggled to determine where
an item would likely be within the ALFWorld environment, due to a lack of commonsense reasoning. Both shortcomings can be addressed in the ReAct paradigm. More details about ReAct-IM is in
Appendix B.2.

## Page 8

An example prompt for ReAct-IM can be found in Appendix C.4, and an example
trajectory in Appendix D.2.3.
2. [research:react_pdf / page 4 / Page 4]
   ## Page 4

appear sparsely in the most relevant positions of a trajectory, so we let the language model decide the
asynchronous occurrence of thoughts and actions for itself. Since decision making and reasoning capabilities are integrated into a large language model, ReAct
enjoys several unique features: A) Intuitive and easy to design : Designing ReAct prompts is
straightforward as human annotators just type down their thoughts in language on top of their actions
taken.
3. [research:react_pdf / page 15 / Page 15]
   ## Page 15

(a) ReAct
trajectory fails due to a hallucinating thought (Act 17). (b) By a human simply editing two thoughts
(Act 17, 23), the ReAct trajectory produces desirable reasoning traces and actions and succeeds. is difﬁcult for Act and previous RL methods, as a human cannot change the model parameters, and
changing a few actions might not edit the rest of the model behavior. This paradigm is also more than
human dialogue to update the goal or subgoal as in Huang et al.
4. [research:react_pdf / page 4 / Page 4]
   ## Page 4

3.2 M ETHODS
ReAct Prompting For HotpotQA and Fever, we randomly select 6 and 3 cases2 from the training
set and manually compose ReAct-format trajectories to use as few-shot exemplars in the prompts. Similar to Figure 1(d), each trajectory consists of multiple thought-action-observation steps (i.e. dense
thought), where free-form thoughts are used for various purposes.
5. [research:react_pdf / page 14 / Page 14]
   ## Page 14

Only ReAct is
able to obtain the up-to-date answer thanks to real-world web interaction plus reasoning. During trajectory inspection, we also ﬁnd that sometimesReAct does not agree with dataset labels as
the labels themselves could be outdated. For example, as shown in Figure 4, the question asks about
the size of a hotel, which increased from the HotpotQA construction time.
6. [research:react_pdf / page 2 / Page 2]
   ## Page 2

ReAct
prompts LLMs to generate both verbal reasoning traces and actions pertaining to a task in an
interleaved manner, which allows the model to perform dynamic reasoning to create, maintain, and
adjust high-level plans for acting (reason to act), while also interact with the external environments
(e.g. Wikipedia) to incorporate additional information into reasoning (act to reason).
7. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

Further, ReAct + Reflexion
learns to solve additional tasks by learning in 12 consecutive trials. In the ReAct-only approach, we
see that performance increase halts between trials 6 and 7. Analysis A common error in baseline failed AlfWorld trajectories is when an agent thinks that it
has possession of an item but does not actually have the item. The agent proceeds to execute several
actions in a long trajectory and is not able to backtrack its actions to find the mistake. Reflexion
8. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

To avoid syntactic errors, we provide two domain-specific few-shot trajectories to the agent. We use
the same few-shot trajectory examples as Yao et al.[30] with GPT-3 for the LLM. AlfWorld tasks,
ReAct few-shot prompts, and Reflexion examples are included in the appendix. Results ReAct + Reflexion significantly outperforms ReAct by completing 130 out of 134 tasks
using the simple heuristic to detect hallucinations and inefficient planning.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-react-grounding

Query:
ReAct 在问答任务中怎样减少 hallucination 和 error propagation？

Reference Answer Points:
- 通过行动与外部 Wikipedia API 交互来检索信息
- 外部信息为推理提供事实依据并减少幻觉和错误传播

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 1 / Page 1]
   ## Page 1

We apply our
approach, named ReAct, to a diverse set of language and decision making tasks
and demonstrate its effectiveness over state-of-the-art baselines in addition to
improved human interpretability and trustworthiness.

## Page 1

Concretely, on question
answering (HotpotQA) and fact veriﬁcation (Fever), ReAct overcomes prevalent
issues of hallucination and error propagation in chain-of-thought reasoning by
interacting with a simple Wikipedia API, and generating human-like task-solving
trajectories that are more interpretable than baselines without reasoning traces.

## Page 1

Furthermore, on two interactive decision making benchmarks (ALFWorld and
WebShop), ReAct outperforms imitation and reinforcement learning methods by
an absolute success rate of 34% and 10% respectively, while being prompted with
only one or two in-context examples.
2. [research:react_pdf / page 6 / Page 6]
   ## Page 6

To better understand the behavioral difference between ReAct and CoT on HotpotQA, we
randomly sampled 50 trajectories with correct and incorrect answers (judged by EM) from ReAct
and CoT respectively (thus 200 examples in total), and manually labeled their success and failure
modes in Table 2. Some key observations are as follows:
A) Hallucination is a serious problem for CoT, resulting in much higher false positive rate than
ReAct (14% vs. 6%) in success mode, and make up its major failure mode (56%).
3. [research:react_pdf / page 2 / Page 2]
   ## Page 2

However, this “chain-of-thought” reasoning is a static black box, in that the model uses
its own internal representations to generate thoughts and is not grounded in the external world,
which limits its ability to reason reactively or update its knowledge. This can lead to issues like fact
hallucination and error propagation over the reasoning process (Figure 1 (1b)).
4. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

On the other hand, 3 shows a ReAct-only agent
converging at a hallucination rate of 22% with no signs of long-term recovery. 4.2 Reasoning: HotpotQA
HotPotQA [28] is a Wikipedia-based dataset with 113k question-and-answer pairs that challenge
agents to parse content and reason over several supporting documents.
5. [research:react_pdf / page 14 / Page 14]
   ## Page 14

Figure 5 shows that by simply removing a hallucinating sentence in Act
17 and adding some hints in Act 23, ReAct can be made to change its behavior drastically to align
with these human thought edits and succeed in the task. From a human perspective, solving such a
task becomes signiﬁcantly easier, from typing tens of actions to only editing a couple of thoughts,
which enables new forms of human-machine collaboration. We note that such a policy edit on-the-go
6. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

0 2 4 6 8 10
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Environments
(a) ALFWorld Success Rate
ReAct only
ReAct + Reflexion (Heuristic)
ReAct + Reflexion (GPT)
0 2 4 6 8 10
Trial Number
0.0
0.1
0.2
0.3
0.4
0.5Proportion of Environments
(a) ALFWorld Success Rate
ReAct only - hallucination
ReAct only - inefficient planning
ReAct + Reflexion - hallucination
ReAct + Reflexion - inefficient planning
Figure 3: (a) AlfWorld performance across 134 tasks showing cumulative proportions of solved tasks
using self-evaluation techniques of (Heuristic) and (GPT) for binary classification.
7. [research:react_pdf / page 15 / Page 15]
   ## Page 15

(a) ReAct
trajectory fails due to a hallucinating thought (Act 17). (b) By a human simply editing two thoughts
(Act 17, 23), the ReAct trajectory produces desirable reasoning traces and actions and succeeds. is difﬁcult for Act and previous RL methods, as a human cannot change the model parameters, and
changing a few actions might not edit the rest of the model behavior. This paradigm is also more than
human dialogue to update the goal or subgoal as in Huang et al.
8. [research:react_pdf / page 14 / Page 14]
   ## Page 14

WhileStandard and CoT
give wrong answers due to hallucination, Act fails despite the access of real-world web interaction,
due to a lack of reasoning to guide how to interact with the Internet for QA. Only ReAct is able to
retrieve up-to-date information from the Internet and provide a reasonable answer.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-reflexion-memory

Query:
Reflexion 的短期记忆和长期记忆分别保存什么？

Reference Answer Points:
- trajectory history 作为短期记忆
- 自我反思文本存入长期记忆并用于后续试次

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

to the way that humans remember fine-grain recent details while also recalling distilled important
experiences from long-term memory. In the RL setup, the trajectory history serves as the short-term
memory while outputs from the Self-Reflection model are stored in long-term memory. These two
memory components work together to provide context that is specific but also influenced by lessons
learned over several trials, which is a key advantage of Reflexion agents over other LLM action
choice works.

## Page 5

The Reflexion process Reflexion is formalized as an iterative optimization process in 1. In the
first trial, the Actor produces a trajectory τ0 by interacting with the environment. The Evaluator then
produces a score r0 which is computed as rt = Me(τ0). rt is only a scalar reward for trial t that
improves as task-specific performance increases.
2. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
3. [research:reflexion_pdf / page 9 / Page 9]
   ## Page 9

In this study, we limit long-term memory to
a sliding window with maximum capacity, but we encourage future work to extend the memory
component of Reflexion with more advanced structures such as vector embedding databases or
traditional SQL databases.
4. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

This iterative
process of trial, error, self-reflection, and persisting memory enables the agent to rapidly improve its
decision-making ability in various environments by utilizing informative feedback signals. Memory Core components of the Reflexion process are the notion of short-term and long-term
memory. At inference time, the Actor conditions its decisions on short and long-term memory, similar
5. [research:reflexion_pdf / page 1 / Page 1]
   ## Page 1

Concretely, Reflexion agents verbally reflect
on task feedback signals, then maintain their own reflective text in an episodic
memory buffer to induce better decision-making in subsequent trials. Reflexion is
flexible enough to incorporate various types (scalar values or free-form language)
and sources (external or internally simulated) of feedback signals, and obtains
significant improvements over a baseline agent across diverse tasks (sequential
decision-making, coding, language reasoning).
6. [research:reflexion_pdf / page 15 / Page 15]
   ## Page 15

Reflexion Self-Reflection generations follow the form:
(Instruction)
(Function implementation)
(Unit test feedback)
C.4 Reflexion programming no Self-Reflection ablation example
Reflexion no Self-Reflection ablation Actor generations follow the form:
(Instruction)
(Function implementation)
(Unit test feedback)
(Self-reflection)
(Instruction for next function implmentation)
C.5 Reflexion programming no test generation ablation example
Reflexion no test generation ablation Actor generations follow the form:
(Instruction)
7. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

Self-reflection The Self-Reflection model instantiated as an LLM, plays a crucial role in the
Reflexion framework by generating verbal self-reflections to provide valuable feedback for future
trials. Given a sparse reward signal, such as a binary success status (success/fail), the current trajectory,
and its persistent memory mem, the self-reflection model generates nuanced and specific feedback. This feedback, which is more informative than scalar rewards, is then stored in the agent’s memory
(mem).
8. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

In the baseline runs, if self-reflection is suggested,
we skip the self-reflection process, reset the environment, and start a new trial. In the Reflexion runs,
the agent uses self-reflection to find its mistake, update its memory, reset the environment, and start a
new trial. To avoid very long prompt windows that may exceed the maximum limit, we truncate the
agent’s memory to the last 3 self-reflections (experiences).

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: single-reflexion-loop

Query:
Actor、Evaluator、Self-Reflection model 和 memory 如何跨 trial 协作？

Reference Answer Points:
- Actor 根据状态和记忆生成 trajectory
- Evaluator 对 trajectory 给出反馈
- Self-Reflection model 分析反馈与 trajectory 并产生反思
- 反思存入 memory 并影响下一 trial

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

The Reflexion process Reflexion is formalized as an iterative optimization process in 1. In the
first trial, the Actor produces a trajectory τ0 by interacting with the environment. The Evaluator then
produces a score r0 which is computed as rt = Me(τ0). rt is only a scalar reward for trial t that
improves as task-specific performance increases.

## Page 5

After the first trial, to amplify r0 to a feedback form
that can be used for improvement by an LLM, the Self-Reflection model analyzes the set of {τ0, r0}
to produce a summary sr0 which is stored in the memory mem. srt is a verbal experience feedback
for trial t. The Actor, Evaluator, and Self-Reflection models work together through trials in a loop
until the Evaluator deems τt to be correct. As mentioned in 3, the memory component of Reflexion
is crucial to its effectiveness.

## Page 5

After each trial t, srt, is appended mem. In practice, we bound mem
by a maximum number of stored experiences, Ω (usually set to 1-3) to adhere to max context LLM
limitations. 4 Experiments
We evaluate various natural language RL setups on decision-making, reasoning, and code generation
tasks.
2. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

ActionObs / Reward
Trajectory
(short-term memory)
Experience
(long-term memory)
Self-reflection (LM)
Agent
Actor (LM)
Environment
Evaluator (LM)
External feedback
Internal
feedback
Reflective
text
Algorithm 1 Reinforcement via self-reflection
Initialize Actor, Evaluator, Self-Reflection:
Ma, Me, Msr
Initialize policy πθ(ai|si), θ = {Ma, mem}
Generate initial trajectory using πθ
Evaluate τ0 using Me
Generate initial self-reflection sr0 using Msr
Set mem ← [sr0]
Set t = 0
while Me not pass or t <max trials do
Generate τt = [a0, o0, .
3. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

This iterative
process of trial, error, self-reflection, and persisting memory enables the agent to rapidly improve its
decision-making ability in various environments by utilizing informative feedback signals. Memory Core components of the Reflexion process are the notion of short-term and long-term
memory. At inference time, the Actor conditions its decisions on short and long-term memory, similar
4. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

Self-reflection The Self-Reflection model instantiated as an LLM, plays a crucial role in the
Reflexion framework by generating verbal self-reflections to provide valuable feedback for future
trials. Given a sparse reward signal, such as a binary success status (success/fail), the current trajectory,
and its persistent memory mem, the self-reflection model generates nuanced and specific feedback. This feedback, which is more informative than scalar rewards, is then stored in the agent’s memory
(mem).
5. [research:reflexion_pdf / page 3 / Page 3]
   ## Page 3

CodeT does not access
hidden test cases but does not implement a self-learning step to improve code writing. 3 Reflexion: reinforcement via verbal reflection
We develop a modular formulation for Reflexion, utilizing three distinct models: an Actor, denoted as
Ma, which generates text and actions; anEvaluator model, represented by Me, that scores the outputs
produced by Ma; and a Self-Reflection model, denoted as Msr, which generates verbal reinforcement
cues to assist the Actor in self-improvement.
6. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

In the baseline runs, if self-reflection is suggested,
we skip the self-reflection process, reset the environment, and start a new trial. In the Reflexion runs,
the agent uses self-reflection to find its mistake, update its memory, reset the environment, and start a
new trial. To avoid very long prompt windows that may exceed the maximum limit, we truncate the
agent’s memory to the last 3 self-reflections (experiences).
7. [research:reflexion_pdf / page 3 / Page 3]
   ## Page 3

Kim et al. [10] use a retry pattern over
a fixed number of steps without an evaluation step. Goodman [9] perform a qualitative evaluation
step that proposes optimizations to the previous generation. In this paper, we show that several of
these concepts can be enhanced with self-reflection to build a persisting memory of self-reflective
experiences which allows an agent to identify its own errors and self-suggest lessons to learn from its
mistakes over time.
8. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

The Reflexion process Reflexion is formalized as an iterative optimization process in 1. In the
first trial, the Actor produces a trajectory τ0 by interacting with the environment. The Evaluator then
produces a score r0 which is computed as rt = Me(τ0). rt is only a scalar reward for trial t that
improves as task-specific performance increases.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: compare-react-reflexion-feedback

Query:
比较 ReAct 与 Reflexion 如何利用执行反馈推进后续行为。

Reference Answer Points:
- ReAct 将环境 observation 交错放回当前推理—行动轨迹
- Reflexion 将反馈转成文本反思并存入记忆供后续 episode 使用
- 两者反馈时间尺度与记忆形式不同

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 8 / Page 8]
   ## Page 8

Perhaps the closest prior work is Inner Monologue (IM), from Huang
et al. (2022b), in which actions from an embodied agent are motivated by an eponymous “inner
monologue”. However, IM’s “inner monologue” is limited to observations of the environment
state and what needs to be completed by the agent for the goal to be satisﬁed. In contrast, the
reasoning traces in ReAct for decision making is ﬂexible and sparse, allowing diverse reasoning
types (see Section 2) to be induced for different tasks.

## Page 8

To demonstrate the differences between ReAct and IM, and to highlight the importance of internal
reasoning vs. simple reactions to external feedback, we ran an ablation experiment using a thought
pattern composed of IM-like dense external feedback. As can be seen in Table 3,ReAct substantially
outperforms IM-style prompting ( ReAct-IM) (71 vs. 53 overall success rate), with consistent
advantages on ﬁve out of six tasks.

## Page 8

Qualitatively, we observed that ReAct-IM often made mistakes
in identifying when subgoals were ﬁnished, or what the next subgoal should be, due to a lack of high-
level goal decomposition. Additionally, many ReAct-IM trajectories struggled to determine where
an item would likely be within the ALFWorld environment, due to a lack of commonsense reasoning. Both shortcomings can be addressed in the ReAct paradigm. More details about ReAct-IM is in
Appendix B.2.
2. [research:reflexion_pdf / page 1 / Page 1]
   ## Page 1

However,
it remains challenging for these language agents to quickly and efficiently learn
from trial-and-error as traditional reinforcement learning methods require exten-
sive training samples and expensive model fine-tuning. We propose Reflexion, a
novel framework to reinforce language agents not by updating weights, but in-
stead through linguistic feedback.

## Page 1

Concretely, Reflexion agents verbally reflect
on task feedback signals, then maintain their own reflective text in an episodic
memory buffer to induce better decision-making in subsequent trials. Reflexion is
flexible enough to incorporate various types (scalar values or free-form language)
and sources (external or internally simulated) of feedback signals, and obtains
significant improvements over a baseline agent across diverse tasks (sequential
decision-making, coding, language reasoning).

## Page 1

For example, Reflexion achieves a
91% pass@1 accuracy on the HumanEval coding benchmark, surpassing the previ-
ous state-of-the-art GPT-4 that achieves 80%. We also conduct ablation and analysis
studies using different feedback signals, feedback incorporation methods, and agent
types, and provide insights into how they affect performance. We release all code,
demos, and datasets at https://github.com/noahshinn024/reflexion.
3. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

Further, ReAct + Reflexion
learns to solve additional tasks by learning in 12 consecutive trials. In the ReAct-only approach, we
see that performance increase halts between trials 6 and 7. Analysis A common error in baseline failed AlfWorld trajectories is when an agent thinks that it
has possession of an item but does not actually have the item. The agent proceeds to execute several
actions in a long trajectory and is not able to backtrack its actions to find the mistake. Reflexion
4. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

For example, in figure 1, a Reflexion agent
learns to optimize its own behavior to solve decision-making, programming, and reasoning tasks
through trial, error, and self-reflection. Generating useful reflective feedback is challenging since it requires a good understanding of where
the model made mistakes (i.e. the credit assignment problem [25]) as well as the ability to generate
a summary containing actionable insights for improvement.
5. [research:react_pdf / page 2 / Page 2]
   ## Page 2

ReAct
prompts LLMs to generate both verbal reasoning traces and actions pertaining to a task in an
interleaved manner, which allows the model to perform dynamic reasoning to create, maintain, and
adjust high-level plans for acting (reason to act), while also interact with the external environments
(e.g. Wikipedia) to incorporate additional information into reasoning (act to reason).
6. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

In this paper, we propose an alternative approach called Reflexion that uses verbal reinforcement
to help agents learn from prior failings. Reflexion converts binary or scalar feedback from the
environment into verbal feedback in the form of a textual summary, which is then added as additional
context for the LLM agent in the next episode.
7. [research:react_pdf / page 4 / Page 4]
   ## Page 4

appear sparsely in the most relevant positions of a trajectory, so we let the language model decide the
asynchronous occurrence of thoughts and actions for itself. Since decision making and reasoning capabilities are integrated into a large language model, ReAct
enjoys several unique features: A) Intuitive and easy to design : Designing ReAct prompts is
straightforward as human annotators just type down their thoughts in language on top of their actions
taken.
8. [research:reflexion_pdf / page 3 / Page 3]
   ## Page 3

Related work on reasoning and decision-making
Approach Self Hidden Decision Binary Memory
refine constraints making reward
Self-refine [15] ✓ ✗ ✗ ✗ ✗
Beam search [27] ✓ ✓ ✓ ✓ ✗
Reflexion (ours) ✓ ✓ ✓ ✓ ✓
Related work on programming
Approach Test Debugging Self-generated Multiple Self-reflection
Test execution execution tests languages
AlphaCode [14] ✓ ✗ ✗ ✓ ✗
CodeT [5] ✓ ✗ ✓ ✗ ✗
Self-debugging [7] ✓ ✓ ✗ ✗ ✗
CodeRL [12] ✓ ✓ ✗ ✗ ✗
Reflexion (ours) ✓ ✓ ✓ ✓ ✓
[16] use decider models to reason over several generations.
9. [research:react_pdf / page 6 / Page 6]
   ## Page 6

To better understand the behavioral difference between ReAct and CoT on HotpotQA, we
randomly sampled 50 trajectories with correct and incorrect answers (judged by EM) from ReAct
and CoT respectively (thus 200 examples in total), and manually labeled their success and failure
modes in Table 2. Some key observations are as follows:
A) Hallucination is a serious problem for CoT, resulting in much higher false positive rate than
ReAct (14% vs. 6%) in success mode, and make up its major failure mode (56%).
10. [research:reflexion_pdf / page 9 / Page 9]
   ## Page 9

8 Reproducibility
We highly advise others to use isolated execution environments when running autonomous code
writing experiments as the generated code is not validated before execution.
11. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

The Reflexion process Reflexion is formalized as an iterative optimization process in 1. In the
first trial, the Actor produces a trajectory τ0 by interacting with the environment. The Evaluator then
produces a score r0 which is computed as rt = Me(τ0). rt is only a scalar reward for trial t that
improves as task-specific performance increases.
12. [research:reflexion_pdf / page 14 / Page 14]
   ## Page 14

0.0 0.5 1.0 1.5 2.0 2.5 3.0
Trial Number
0.10
0.15
0.20
0.25
0.30
0.35
0.40
0.45
0.50Proportion of Solved Environments
WebShop Success Rate
ReAct only
ReAct + Reflexion
Figure 6: Reflexion vs React performance on WebShop across 100 customer shopping requests. ReAct + Reflexion fails to significantly outperform ReAct. C Programming
Programming LLM calls require strict instructions to produce function bodies only, due to the
extensive dialogue training of the LLMs.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: compare-react-reflexion-memory

Query:
ReAct 的 trajectory 与 Reflexion 的 episodic memory 在作用上有什么不同？

Reference Answer Points:
- ReAct trajectory 在一次交互中交错包含 Thought、Act 和 Observation
- Reflexion 将反思作为可解释的 episodic memory 跨试次保留
- 前者支撑当前行动循环，后者为未来 episode 提供提示

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

0 2 4 6
Trial Number
0.2
0.4
0.6
0.8Proportion of Solved Tasks
(a) HotPotQA Success Rate
CoT only
ReAct only
CoT + Reflexion
ReAct + Reflexion
0 1 2 3 4 5 6 7
Trial Number
0.4
0.6
0.8
1.0Proportion of Solved Tasks
(b) HotPotQA CoT (GT)
CoT (GT) only
CoT (GT) + Reflexion
0 1 2 3 4
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Tasks
(c) HotPotQA Episodic Memory
CoT (GT) only
CoT (GT) EPM
CoT (GT) EPM + Reflexion
Figure 4: Chain-of-Thought (CoT) and ReAct.

## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.

## Page 7

Recall that CoT (GT) uses Chain-of-Thought
reasoning with provided ground truth context, which tests reasoning ability over long contexts. Next,
we add an element of episodic memory (EPM) by including the most recent trajectory. For the
Reflexion agent, we implement the standard self-reflection step as a final pass. Intuitively, we test if
the agent is iteratively learning more effectively by using verbal explanation using language written
in the first person.
2. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

to the way that humans remember fine-grain recent details while also recalling distilled important
experiences from long-term memory. In the RL setup, the trajectory history serves as the short-term
memory while outputs from the Self-Reflection model are stored in long-term memory. These two
memory components work together to provide context that is specific but also influenced by lessons
learned over several trials, which is a key advantage of Reflexion agents over other LLM action
choice works.
3. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

Further, ReAct + Reflexion
learns to solve additional tasks by learning in 12 consecutive trials. In the ReAct-only approach, we
see that performance increase halts between trials 6 and 7. Analysis A common error in baseline failed AlfWorld trajectories is when an agent thinks that it
has possession of an item but does not actually have the item. The agent proceeds to execute several
actions in a long trajectory and is not able to backtrack its actions to find the mistake. Reflexion
4. [research:reflexion_pdf / page 1 / Page 1]
   ## Page 1

Concretely, Reflexion agents verbally reflect
on task feedback signals, then maintain their own reflective text in an episodic
memory buffer to induce better decision-making in subsequent trials. Reflexion is
flexible enough to incorporate various types (scalar values or free-form language)
and sources (external or internally simulated) of feedback signals, and obtains
significant improvements over a baseline agent across diverse tasks (sequential
decision-making, coding, language reasoning).
5. [research:react_pdf / page 15 / Page 15]
   ## Page 15

(a) ReAct
trajectory fails due to a hallucinating thought (Act 17). (b) By a human simply editing two thoughts
(Act 17, 23), the ReAct trajectory produces desirable reasoning traces and actions and succeeds. is difﬁcult for Act and previous RL methods, as a human cannot change the model parameters, and
changing a few actions might not edit the rest of the model behavior. This paradigm is also more than
human dialogue to update the goal or subgoal as in Huang et al.
6. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Recall that CoT (GT) uses Chain-of-Thought
reasoning with provided ground truth context, which tests reasoning ability over long contexts. Next,
we add an element of episodic memory (EPM) by including the most recent trajectory. For the
Reflexion agent, we implement the standard self-reflection step as a final pass. Intuitively, we test if
the agent is iteratively learning more effectively by using verbal explanation using language written
in the first person.
7. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

0 2 4 6
Trial Number
0.2
0.4
0.6
0.8Proportion of Solved Tasks
(a) HotPotQA Success Rate
CoT only
ReAct only
CoT + Reflexion
ReAct + Reflexion
0 1 2 3 4 5 6 7
Trial Number
0.4
0.6
0.8
1.0Proportion of Solved Tasks
(b) HotPotQA CoT (GT)
CoT (GT) only
CoT (GT) + Reflexion
0 1 2 3 4
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Tasks
(c) HotPotQA Episodic Memory
CoT (GT) only
CoT (GT) EPM
CoT (GT) EPM + Reflexion
Figure 4: Chain-of-Thought (CoT) and ReAct.
8. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

This iterative
process of trial, error, self-reflection, and persisting memory enables the agent to rapidly improve its
decision-making ability in various environments by utilizing informative feedback signals. Memory Core components of the Reflexion process are the notion of short-term and long-term
memory. At inference time, the Actor conditions its decisions on short and long-term memory, similar

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: compare-attention-react-information

Query:
比较 Transformer self-attention 与 ReAct 外部行动在获取信息方面的机制。

Reference Answer Points:
- self-attention 用 query-key compatibility 对序列内部 values 加权聚合
- ReAct 通过 action 与外部环境或知识源交互获取额外信息
- 一个在给定序列内部计算表示，一个主动从外部来源增加观察

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 9 / Page 9]
   ## Page 9

STaR (Zelikman et al., 2022) bootstraps the reasoning process by
ﬁnetuning the model on correct rationales generated by the model itself. Faithful reasoning (Creswell
& Shanahan, 2022) decomposes multi-step reasoning into three steps, each performed by a dedicated
LM respectively. Similar approaches like Scratchpad (Nye et al., 2021), which ﬁnetunes a LM on
intermediate computation steps, also demonstrate improvement on multi-step computation problems.

## Page 9

In contrast to these methods, ReAct performs more than just isolated, ﬁxed reasoning, and integrates
model actions and their corresponding observations into a coherent stream of inputs for the model to
reason more accurately and tackle tasks beyond reasoning (e.g. interactive decision making).

## Page 9

Language model for decision making The strong capability of LLMs has enabled them to perform
tasks beyond language generation, and it is becoming more popular to take advantage of LLMs as a
policy model for decision making, especially in interactive environments. WebGPT (Nakano et al.,
2021) uses an LM to interact with web browsers, navigate through web pages, and infer answers to
complicated questions from ELI5 (Fan et al., 2019).
2. [research:attention_pdf / page 2 / Page 2]
   ## Page 2

This makes
it more difficult to learn dependencies between distant positions [ 12]. In the Transformer this is
reduced to a constant number of operations, albeit at the cost of reduced effective resolution due
to averaging attention-weighted positions, an effect we counteract with Multi-Head Attention as
described in section 3.2. Self-attention, sometimes called intra-attention is an attention mechanism relating different positions
of a single sequence in order to compute a representation of the sequence.
3. [research:react_pdf / page 7 / Page 7]
   ## Page 7

Act prompts are constructed using
the same trajectories, but without thoughts — since task instances are randomly chosen from the
training set, it favors neitherReAct nor Act and provides a fair and controlled comparison to test the
importance of sparse thoughts. For baselines, we use BUTLER (Shridhar et al., 2020b), an imitation
learning agent trained on 105 expert trajectories for each task type5. WebShop Can ReAct also interact with noisy real-world language environments for practical
applications?
4. [research:react_pdf / page 3 / Page 3]
   ## Page 3

limited support of reasoning and acting behaviors), and perform initial ﬁnetuning
experiments showing the potential of ReAct to improve with additional training data. Scaling up
ReAct to train and operate on more tasks and combining it with complementary paradigms like
reinforcement learning could further unlock the potential of large language models. 2 REAC T: S YNERGIZING REASONING + AC TING
Consider a general setup of an agent interacting with an environment for task solving.
5. [research:react_pdf / page 2 / Page 2]
   ## Page 2

ReAct
prompts LLMs to generate both verbal reasoning traces and actions pertaining to a task in an
interleaved manner, which allows the model to perform dynamic reasoning to create, maintain, and
adjust high-level plans for acting (reason to act), while also interact with the external environments
(e.g. Wikipedia) to incorporate additional information into reasoning (act to reason).
6. [research:attention_pdf / page 2 / Page 2]
   ## Page 2

To the best of our knowledge, however, the Transformer is the first transduction model relying
entirely on self-attention to compute representations of its input and output without using sequence-
aligned RNNs or convolution. In the following sections, we will describe the Transformer, motivate
self-attention and discuss its advantages over models such as [17, 18] and [9]. 3 Model Architecture
Most competitive neural sequence transduction models have an encoder-decoder structure [5, 2, 35].
7. [research:react_pdf / page 4 / Page 4]
   ## Page 4

C) Performant and robust: ReAct shows strong generalization to new task instances
while learning solely from one to six in-context examples, consistently outperforming baselines with
only reasoning or acting across different domains. We also show in Section 3 additional beneﬁts
when ﬁnetuning is enabled, and in Section 4 how ReAct performance is robust to prompt selections.
8. [research:react_pdf / page 9 / Page 9]
   ## Page 9

Perhaps most relevant to ReAct in this respect are SayCan (Ahn et al., 2022)
and Inner Monologue (Huang et al., 2022b), which use LLMs for robotic action planning and decision
making. In SayCan, LLMs were prompted to directly predict possible actions a robot can take, which
is then reranked by an affordance model grounded on the visual environments for ﬁnal prediction.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: compare-react-reflexion-components

Query:
从生成组件和环境反馈来源角度比较 ReAct 与 Reflexion。

Reference Answer Points:
- ReAct 中 Thought 和 Act 由模型生成而 Observation 来自环境
- Reflexion 模块化形式包含 Actor、Evaluator 与 Self-Reflection model
- Reflexion 的 evaluator feedback 与反思记忆形成跨 trial 循环

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 14 / Page 14]
   ## Page 14

In HotPotQA,
the agent faces a similar WebShop search query task but is more successful as the search space for
Wikipedia articles is more diverse and requires less precise search queries. A common problem for
e-commerce search engines is properly handling ambiguity in natural language search interpretations. Thus, WebShop presents a task that requires very diverse and unique behavior from a Reflexion agent.

## Page 14

0.0 0.5 1.0 1.5 2.0 2.5 3.0
Trial Number
0.10
0.15
0.20
0.25
0.30
0.35
0.40
0.45
0.50Proportion of Solved Environments
WebShop Success Rate
ReAct only
ReAct + Reflexion
Figure 6: Reflexion vs React performance on WebShop across 100 customer shopping requests. ReAct + Reflexion fails to significantly outperform ReAct. C Programming
Programming LLM calls require strict instructions to produce function bodies only, due to the
extensive dialogue training of the LLMs.

## Page 14

A few programming examples are reported below with
instructions highlighted in blue and templates. See the full implementation at https://github. com/noahshinn024/reflexion. C.1 Programming function implementation example (HumanEval Python)
Sample function signature:
1 def minSubArraySum ( nums ):
2 """
3 Given an array of integers nums , find the minimum sum of
any
4 non - empty sub - array of nums . 5 Example
6 minSubArraySum ([2 , 3, 4, 1, 2, 4]) == 1
2. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
3. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

Further, ReAct + Reflexion
learns to solve additional tasks by learning in 12 consecutive trials. In the ReAct-only approach, we
see that performance increase halts between trials 6 and 7. Analysis A common error in baseline failed AlfWorld trajectories is when an agent thinks that it
has possession of an item but does not actually have the item. The agent proceeds to execute several
actions in a long trajectory and is not able to backtrack its actions to find the mistake. Reflexion
4. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

0 2 4 6 8 10
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Environments
(a) ALFWorld Success Rate
ReAct only
ReAct + Reflexion (Heuristic)
ReAct + Reflexion (GPT)
0 2 4 6 8 10
Trial Number
0.0
0.1
0.2
0.3
0.4
0.5Proportion of Environments
(a) ALFWorld Success Rate
ReAct only - hallucination
ReAct only - inefficient planning
ReAct + Reflexion - hallucination
ReAct + Reflexion - inefficient planning
Figure 3: (a) AlfWorld performance across 134 tasks showing cumulative proportions of solved tasks
using self-evaluation techniques of (Heuristic) and (GPT) for binary classification.
5. [research:reflexion_pdf / page 15 / Page 15]
   ## Page 15

Reflexion Self-Reflection generations follow the form:
(Instruction)
(Function implementation)
(Unit test feedback)
C.4 Reflexion programming no Self-Reflection ablation example
Reflexion no Self-Reflection ablation Actor generations follow the form:
(Instruction)
(Function implementation)
(Unit test feedback)
(Self-reflection)
(Instruction for next function implmentation)
C.5 Reflexion programming no test generation ablation example
Reflexion no test generation ablation Actor generations follow the form:
(Instruction)
6. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

0 2 4 6
Trial Number
0.2
0.4
0.6
0.8Proportion of Solved Tasks
(a) HotPotQA Success Rate
CoT only
ReAct only
CoT + Reflexion
ReAct + Reflexion
0 1 2 3 4 5 6 7
Trial Number
0.4
0.6
0.8
1.0Proportion of Solved Tasks
(b) HotPotQA CoT (GT)
CoT (GT) only
CoT (GT) + Reflexion
0 1 2 3 4
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Tasks
(c) HotPotQA Episodic Memory
CoT (GT) only
CoT (GT) EPM
CoT (GT) EPM + Reflexion
Figure 4: Chain-of-Thought (CoT) and ReAct.
7. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

To avoid syntactic errors, we provide two domain-specific few-shot trajectories to the agent. We use
the same few-shot trajectory examples as Yao et al.[30] with GPT-3 for the LLM. AlfWorld tasks,
ReAct few-shot prompts, and Reflexion examples are included in the appendix. Results ReAct + Reflexion significantly outperforms ReAct by completing 130 out of 134 tasks
using the simple heuristic to detect hallucinations and inefficient planning.
8. [research:reflexion_pdf / page 1 / Page 1]
   ## Page 1

Concretely, Reflexion agents verbally reflect
on task feedback signals, then maintain their own reflective text in an episodic
memory buffer to induce better decision-making in subsequent trials. Reflexion is
flexible enough to incorporate various types (scalar values or free-form language)
and sources (external or internally simulated) of feedback signals, and obtains
significant improvements over a baseline agent across diverse tasks (sequential
decision-making, coding, language reasoning).

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: session-attention-why

Query:
它为什么这样设计？

Reference Answer Points:
- dk 较大时点积幅度增大
- 大点积会把 softmax 推入梯度极小区域，因此进行缩放

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

Scaled Dot-Product Attention
Multi-Head Attention
Figure 2: (left) Scaled Dot-Product Attention. (right) Multi-Head Attention consists of several
attention layers running in parallel. of the values, where the weight assigned to each value is computed by a compatibility function of the
query with the corresponding key. 3.2.1 Scaled Dot-Product Attention
We call our particular attention "Scaled Dot-Product Attention" (Figure 2).

## Page 4

The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values. In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V .
2. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

While the two are similar in theoretical complexity, dot-product attention is
much faster and more space-efficient in practice, since it can be implemented using highly optimized
matrix multiplication code. While for small values of dk the two mechanisms perform similarly, additive attention outperforms
dot product attention without scaling for larger values of dk [3].
3. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

We compute
the matrix of outputs as:
Attention(Q, K, V) = softmax(QKT
√dk
)V (1)
The two most commonly used attention functions are additive attention [2], and dot-product (multi-
plicative) attention. Dot-product attention is identical to our algorithm, except for the scaling factor
of 1√dk
. Additive attention computes the compatibility function using a feed-forward network with
a single hidden layer.
4. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

On each of these projected versions of
queries, keys and values we then perform the attention function in parallel, yielding dv-dimensional
4To illustrate why the dot products get large, assume that the components of q and k are independent random
variables with mean 0 and variance 1. Then their dot product, q · k = Pdk
i=1 qiki, has mean 0 and variance dk.
5. [research:attention_pdf / page 4 / Page 4]
   ## Page 4

The input consists of
queries and keys of dimension dk, and values of dimension dv. We compute the dot products of the
query with all keys, divide each by √dk, and apply a softmax function to obtain the weights on the
values. In practice, we compute the attention function on a set of queries simultaneously, packed together
into a matrix Q. The keys and values are also packed together into matrices K and V .
6. [research:attention_pdf / page 5 / Page 5]
   ## Page 5

We need to prevent leftward
information flow in the decoder to preserve the auto-regressive property. We implement this
inside of scaled dot-product attention by masking out (setting to −∞) all values in the input
of the softmax which correspond to illegal connections. See Figure 2.
7. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
8. [research:attention_pdf / page 1 / Page 1]
   ## Page 1

Jakob proposed replacing RNNs with self-attention and started
the effort to evaluate this idea. Ashish, with Illia, designed and implemented the first Transformer models and
has been crucially involved in every aspect of this work. Noam proposed scaled dot-product attention, multi-head
attention and the parameter-free position representation and became the other person involved in nearly every
detail.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: session-react-feedback

Query:
它的反馈机制是什么？

Reference Answer Points:
- 行动从环境获得 Observation
- Observation 进入后续推理并帮助更新计划

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

To test improvement in
reasoning only ability, we implement Reflexion + Chain-of-Thought (CoT) [ 26] for step-by-step
Q → A and Q, Cgt → A implementations, where Q is the question, Cgt is the ground truth context
from the dataset, and A is the final answer. Since CoT is not a multi-step decision-making technique,
we give Cgt to the agent so that we can isolate the reasoning behavior over large sections of the
provided text.

## Page 6

To test holistic question and answering ability, which requires reasoning and action
choice, we implement a Reflexion + ReAct [ 30] agent that can retrieve relevant context using a
Wikipedia API and infer answers using step-by-step explicit thinking. For CoT implementations, we
use 6-shot prompting; for ReAct, we use 2-shot prompting, and for self-reflection, we use 2-shot
prompting. All examples can be found in the appendix. Robustly evaluating natural language answers is a long-standing problem in NLP.

## Page 6

Therefore, between
trials, we use exact match answer grading using the environment to give a binary success signal to
the agent. After each trial, the self-reflection loop is employed to amplify the binary signal, similar to
the decision-making setup 4.1 in AlfWorld with a memory size of 3 experiences. Results Reflexion outperforms all baseline approaches by significant margins over several learning
steps.
2. [research:react_pdf / page 3 / Page 3]
   ## Page 3

To summarize, our key contributions are the following: (1) we introduce ReAct, a novel prompt-
based paradigm to synergize reasoning and acting in language models for general task solving; (2) we
perform extensive experiments across diverse benchmarks to showcase the advantage ofReAct in a
few-shot learning setup over prior approaches that perform either reasoning or action generation in
isolation; (3) we present systematic ablations and analysis to understand the importance of acting in
reasoning tasks, and reasoning in interactive tasks; (4) we analyze the limitations ofReAct under the
prompting setup (i.e.
3. [research:react_pdf / page 2 / Page 2]
   ## Page 2

ReAct
prompts LLMs to generate both verbal reasoning traces and actions pertaining to a task in an
interleaved manner, which allows the model to perform dynamic reasoning to create, maintain, and
adjust high-level plans for acting (reason to act), while also interact with the external environments
(e.g. Wikipedia) to incorporate additional information into reasoning (act to reason).
4. [research:react_pdf / page 15 / Page 15]
   ## Page 15

B.2 A LFWORLD IM-S TYLE DETAILS
For the IM-style ablation, the same expert trajectories used in ReAct are reannotated with dense
external feedback thoughts within these trajectories, that limit ReAct-IM to only think about (1)
decomposing the current goal and (2) the current subgoal that needs to be completed.
5. [research:react_pdf / page 6 / Page 6]
   ## Page 6

we note that there is one frequent
error pattern speciﬁc to ReAct, in which the model repetitively generates the previous thoughts and
actions, and we categorize it as part of “reasoning error” as the model fails to reason about what the
proper next action to take and jump out of the loop4. C) For ReAct, successfully retrieving informative knowledge via search is critical.
6. [research:react_pdf / page 5 / Page 5]
   ## Page 5

internal knowledge might not support the task conﬁdently), back off to ReAct. Finetuning Due to the challenge of manually annotating reasoning traces and actions at scale,
we consider a bootstraping approach similar to Zelikman et al. (2022), using 3,000 trajectories
with correct answers generated by ReAct (also for other baselines) to ﬁnetune smaller language
models (PaLM-8/62B) to decode trajectories (all thoughts, actions, observations) conditioned on
input questions/claims.
7. [research:react_pdf / page 5 / Page 5]
   ## Page 5

More details are in Appendix B.1. 3.3 R ESULTS AND OBSERVATIONS
ReAct outperforms Act consistently Table 1 shows HotpotQA and Fever results using PaLM-
540B as the base model with different prompting methods. We note that ReAct is better than Act
on both tasks, demonstrating the value of reasoning to guide acting, especially for synthesizing the
ﬁnal answer, as shown in Figure 1 (1c-d). Fine-tuning results 3 also conﬁrm the beneﬁt of reasoning
traces for more informed acting.
8. [research:attention_pdf / page 1 / Page 1]
   ## Page 1

Provided proper attribution is provided, Google hereby grants permission to
reproduce the tables and figures in this paper solely for use in journalistic or
scholarly works. Attention Is All You Need
Ashish Vaswani∗
Google Brain
avaswani@google.com
Noam Shazeer∗
Google Brain
noam@google.com
Niki Parmar∗
Google Research
nikip@google.com
Jakob Uszkoreit∗
Google Research
usz@google.com
Llion Jones∗
Google Research
llion@google.com
Aidan N.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: session-reflexion-why

Query:
为什么？

Reference Answer Points:
- 反思作为 episodic memory 保留以往经验
- 它为未来 episode 的行动提供明确提示

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

to the way that humans remember fine-grain recent details while also recalling distilled important
experiences from long-term memory. In the RL setup, the trajectory history serves as the short-term
memory while outputs from the Self-Reflection model are stored in long-term memory. These two
memory components work together to provide context that is specific but also influenced by lessons
learned over several trials, which is a key advantage of Reflexion agents over other LLM action
choice works.

## Page 5

The Reflexion process Reflexion is formalized as an iterative optimization process in 1. In the
first trial, the Actor produces a trajectory τ0 by interacting with the environment. The Evaluator then
produces a score r0 which is computed as rt = Me(τ0). rt is only a scalar reward for trial t that
improves as task-specific performance increases.
2. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
3. [research:reflexion_pdf / page 1 / Page 1]
   ## Page 1

Concretely, Reflexion agents verbally reflect
on task feedback signals, then maintain their own reflective text in an episodic
memory buffer to induce better decision-making in subsequent trials. Reflexion is
flexible enough to incorporate various types (scalar values or free-form language)
and sources (external or internally simulated) of feedback signals, and obtains
significant improvements over a baseline agent across diverse tasks (sequential
decision-making, coding, language reasoning).
4. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

In the baseline runs, if self-reflection is suggested,
we skip the self-reflection process, reset the environment, and start a new trial. In the Reflexion runs,
the agent uses self-reflection to find its mistake, update its memory, reset the environment, and start a
new trial. To avoid very long prompt windows that may exceed the maximum limit, we truncate the
agent’s memory to the last 3 self-reflections (experiences).
5. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

This iterative
process of trial, error, self-reflection, and persisting memory enables the agent to rapidly improve its
decision-making ability in various environments by utilizing informative feedback signals. Memory Core components of the Reflexion process are the notion of short-term and long-term
memory. At inference time, the Actor conditions its decisions on short and long-term memory, similar
6. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

Self-reflection The Self-Reflection model instantiated as an LLM, plays a crucial role in the
Reflexion framework by generating verbal self-reflections to provide valuable feedback for future
trials. Given a sparse reward signal, such as a binary success status (success/fail), the current trajectory,
and its persistent memory mem, the self-reflection model generates nuanced and specific feedback. This feedback, which is more informative than scalar rewards, is then stored in the agent’s memory
(mem).
7. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

To test holistic question and answering ability, which requires reasoning and action
choice, we implement a Reflexion + ReAct [ 30] agent that can retrieve relevant context using a
Wikipedia API and infer answers using step-by-step explicit thinking. For CoT implementations, we
use 6-shot prompting; for ReAct, we use 2-shot prompting, and for self-reflection, we use 2-shot
prompting. All examples can be found in the appendix. Robustly evaluating natural language answers is a long-standing problem in NLP.
8. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

4 shows that self-reflection improves learning by an 8% absolute boost over
the episodic memory learning advantage. This result supports the argument that refinement-only
approaches are not as effective as self-reflection-guided refinement approaches. 4.3 Programming
We evaluate the baseline and Reflexion approaches on Python and Rust code writing on MBPP
[2], HumanEval [ 6], and LeetcodeHardGym, our new dataset.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: session-method-difference

Query:
这个方法相比前一个方法有什么不同？

Reference Answer Points:
- ReAct 把环境 Observation 用于当前交错推理行动轨迹
- Reflexion 将 evaluator feedback 转成文本反思并跨 episode 存储
- 两者反馈形式与使用时间尺度不同

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

To test improvement in
reasoning only ability, we implement Reflexion + Chain-of-Thought (CoT) [ 26] for step-by-step
Q → A and Q, Cgt → A implementations, where Q is the question, Cgt is the ground truth context
from the dataset, and A is the final answer. Since CoT is not a multi-step decision-making technique,
we give Cgt to the agent so that we can isolate the reasoning behavior over large sections of the
provided text.

## Page 6

To test holistic question and answering ability, which requires reasoning and action
choice, we implement a Reflexion + ReAct [ 30] agent that can retrieve relevant context using a
Wikipedia API and infer answers using step-by-step explicit thinking. For CoT implementations, we
use 6-shot prompting; for ReAct, we use 2-shot prompting, and for self-reflection, we use 2-shot
prompting. All examples can be found in the appendix. Robustly evaluating natural language answers is a long-standing problem in NLP.

## Page 6

Therefore, between
trials, we use exact match answer grading using the environment to give a binary success signal to
the agent. After each trial, the self-reflection loop is employed to amplify the binary signal, similar to
the decision-making setup 4.1 in AlfWorld with a memory size of 3 experiences. Results Reflexion outperforms all baseline approaches by significant margins over several learning
steps.
2. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
3. [research:react_pdf / page 5 / Page 5]
   ## Page 5

More details are in Appendix B.1. 3.3 R ESULTS AND OBSERVATIONS
ReAct outperforms Act consistently Table 1 shows HotpotQA and Fever results using PaLM-
540B as the base model with different prompting methods. We note that ReAct is better than Act
on both tasks, demonstrating the value of reasoning to guide acting, especially for synthesizing the
ﬁnal answer, as shown in Figure 1 (1c-d). Fine-tuning results 3 also conﬁrm the beneﬁt of reasoning
traces for more informed acting.
4. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

After the first trial, to amplify r0 to a feedback form
that can be used for improvement by an LLM, the Self-Reflection model analyzes the set of {τ0, r0}
to produce a summary sr0 which is stored in the memory mem. srt is a verbal experience feedback
for trial t. The Actor, Evaluator, and Self-Reflection models work together through trials in a loop
until the Evaluator deems τt to be correct. As mentioned in 3, the memory component of Reflexion
is crucial to its effectiveness.
5. [research:react_pdf / page 15 / Page 15]
   ## Page 15

B.2 A LFWORLD IM-S TYLE DETAILS
For the IM-style ablation, the same expert trajectories used in ReAct are reannotated with dense
external feedback thoughts within these trajectories, that limit ReAct-IM to only think about (1)
decomposing the current goal and (2) the current subgoal that needs to be completed.
6. [research:react_pdf / page 8 / Page 8]
   ## Page 8

To demonstrate the differences between ReAct and IM, and to highlight the importance of internal
reasoning vs. simple reactions to external feedback, we ran an ablation experiment using a thought
pattern composed of IM-like dense external feedback. As can be seen in Table 3,ReAct substantially
outperforms IM-style prompting ( ReAct-IM) (71 vs. 53 overall success rate), with consistent
advantages on ﬁve out of six tasks.
7. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

In this paper, we propose an alternative approach called Reflexion that uses verbal reinforcement
to help agents learn from prior failings. Reflexion converts binary or scalar feedback from the
environment into verbal feedback in the form of a textual summary, which is then added as additional
context for the LLM agent in the next episode.
8. [research:react_pdf / page 3 / Page 3]
   ## Page 3

To summarize, our key contributions are the following: (1) we introduce ReAct, a novel prompt-
based paradigm to synergize reasoning and acting in language models for general task solving; (2) we
perform extensive experiments across diverse benchmarks to showcase the advantage ofReAct in a
few-shot learning setup over prior approaches that perform either reasoning or action generation in
isolation; (3) we present systematic ablations and analysis to understand the importance of acting in
reasoning tasks, and reasoning in interactive tasks; (4) we analyze the limitations ofReAct under the
prompting setup (i.e.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: cross-session-react

Query:
继续之前的主题：它怎样通过外部信息降低幻觉？

Reference Answer Points:
- ReAct 通过行动查询外部 Wikipedia API
- 检索到的外部事实为后续推理提供 grounding 并减少幻觉和错误传播

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 5 / Page 5]
   ## Page 5

(c) Acting-only prompt (Act), which removes thoughts
in ReAct trajectories, loosely resembling how WebGPT (Nakano et al., 2021) interacts with the
Internet to answer questions, though it operates on a different task and action space, and uses imitation
and reinforcement learning instead of prompting.

## Page 5

Combining Internal and External Knowledge As will be detail in Section 3.3, we observe that
the problem solving process demonstrated by ReAct is more factual and grounded, whereas CoT
is more accurate in formulating reasoning structure but can easily suffer from hallucinated facts
or thoughts.

## Page 5

We therefore propose to incorporate ReAct and CoT-SC, and let the model decide
when to switch to the other method based on the following heuristics: A) ReAct →CoT-SC: when
ReAct fails to return an answer within given steps, back off to CoT-SC. We set 7 and 5 steps for
HotpotQA and FEVER respectively as we ﬁnd more steps will not improve ReAct performance3. B) CoT-SC →ReAct: when the majority answer among nCoT-SC samples occurs less than n/2
times (i.e.
2. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

This self-reflective feedback acts as a ‘semantic’
gradient signal by providing the agent with a concrete direction to improve upon, helping it learn
from prior mistakes to perform better on the task. This is akin to how humans iteratively learn to
accomplish complex tasks in a few-shot manner – by reflecting on their previous failures in order to
form an improved plan of attack for the next attempt.
3. [research:react_pdf / page 9 / Page 9]
   ## Page 9

Inner Monologue made further improvements by adding the eponymous “inner monologue", which is
implemented as injected feedback from the environment. To our knowledge, Inner Monologue is the
ﬁrst work that demonstrates such a closed-loop system, which ReAct builds on. However, we argue
that Inner Monologue does not truly comprise of inner thoughts — this is elaborated in Section 4.
4. [research:react_pdf / page 14 / Page 14]
   ## Page 14

WhileStandard and CoT
give wrong answers due to hallucination, Act fails despite the access of real-world web interaction,
due to a lack of reasoning to guide how to interact with the Internet for QA. Only ReAct is able to
retrieve up-to-date information from the Internet and provide a reasonable answer.
5. [research:react_pdf / page 1 / Page 1]
   ## Page 1

Concretely, on question
answering (HotpotQA) and fact veriﬁcation (Fever), ReAct overcomes prevalent
issues of hallucination and error propagation in chain-of-thought reasoning by
interacting with a simple Wikipedia API, and generating human-like task-solving
trajectories that are more interpretable than baselines without reasoning traces.
6. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

Therefore, between
trials, we use exact match answer grading using the environment to give a binary success signal to
the agent. After each trial, the self-reflection loop is employed to amplify the binary signal, similar to
the decision-making setup 4.1 in AlfWorld with a memory size of 3 experiences. Results Reflexion outperforms all baseline approaches by significant margins over several learning
steps.
7. [research:react_pdf / page 14 / Page 14]
   ## Page 14

Figure 5 shows that by simply removing a hallucinating sentence in Act
17 and adding some hints in Act 23, ReAct can be made to change its behavior drastically to align
with these human thought edits and succeed in the task. From a human perspective, solving such a
task becomes signiﬁcantly easier, from typing tens of actions to only editing a couple of thoughts,
which enables new forms of human-machine collaboration. We note that such a policy edit on-the-go
8. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: cross-session-reflexion

Query:
继续我们之前的分析：它如何把失败变成下一轮可用的信息？

Reference Answer Points:
- 把二元或标量反馈转换成文本反思摘要
- 反思存入记忆并作为下一 episode 的上下文

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

For example, in figure 1, a Reflexion agent
learns to optimize its own behavior to solve decision-making, programming, and reasoning tasks
through trial, error, and self-reflection. Generating useful reflective feedback is challenging since it requires a good understanding of where
the model made mistakes (i.e. the credit assignment problem [25]) as well as the ability to generate
a summary containing actionable insights for improvement.

## Page 2

We explore three ways for doing
this – simple binary environment feedback, pre-defined heuristics for common failure cases, and
self-evaluation such as binary classification using LLMs (decision-making) or self-written unit
tests (programming). In all implementations, the evaluation signal is amplified to natural language
experience summaries which can be stored in long-term memory.

## Page 2

Reflexion has several advantages compared to more traditional RL approaches like policy or value-
based learning: 1) it is lightweight and doesn’t require finetuning the LLM, 2) it allows for more
nuanced forms of feedback (e.g.
2. [research:reflexion_pdf / page 4 / Page 4]
   ## Page 4

For instance, in a multi-step decision-making task, when the agent receives a failure signal, it
can infer that a specific action ai led to subsequent incorrect actions ai+1 and ai+2. The agent can
then verbally state that it should have taken a different action, a′
i, which would have resulted in a′
i+1
and a′
i+2, and store this experience in its memory. In subsequent trials, the agent can leverage its past
experiences to adapt its decision-making approach at time t by choosing action a′
i.
3. [research:react_pdf / page 32 / Page 32]
   ## Page 32

E M ORE ANALYSIS
E.1 S UCCESS AND FAILURE MODES ANALYSIS
We provide some examples corresponding to the success and error mode analysis given in Sec. 3.3. Search results and non-representative steps are omitted to reduce space. Success: True positive
ReAct
Question: Author David Chanoff has collaborated with a U.S. Navy admiral who served as
the ambassador to the United Kingdom under which President? Thought 1: I need to search David Chanoff and find the U.S. Navy admiral he
collaborated with.
4. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

This self-reflective feedback acts as a ‘semantic’
gradient signal by providing the agent with a concrete direction to improve upon, helping it learn
from prior mistakes to perform better on the task. This is akin to how humans iteratively learn to
accomplish complex tasks in a few-shot manner – by reflecting on their previous failures in order to
form an improved plan of attack for the next attempt.
5. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

(b) Classification
of AlfWorld trajectories by reason of failure. eliminates almost all of these cases by using self-reflection to distill long, failed trajectories into
relevant experiences that can are used as "self-hints" in the future. There are two main cases in which
long-term memory helps an agent in AlfWorld: 1) An early mistake in a long trajectory can be easily
identified. The agent can suggest a new action choice or even a new long-term plan.
6. [research:reflexion_pdf / page 3 / Page 3]
   ## Page 3

Kim et al. [10] use a retry pattern over
a fixed number of steps without an evaluation step. Goodman [9] perform a qualitative evaluation
step that proposes optimizations to the previous generation. In this paper, we show that several of
these concepts can be enhanced with self-reflection to build a persisting memory of self-reflective
experiences which allows an agent to identify its own errors and self-suggest lessons to learn from its
mistakes over time.
7. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

In this paper, we propose an alternative approach called Reflexion that uses verbal reinforcement
to help agents learn from prior failings. Reflexion converts binary or scalar feedback from the
environment into verbal feedback in the form of a textual summary, which is then added as additional
context for the LLM agent in the next episode.
8. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

Therefore, between
trials, we use exact match answer grading using the environment to give a binary success signal to
the agent. After each trial, the self-reflection loop is employed to amplify the binary signal, similar to
the decision-making setup 4.1 in AlfWorld with a memory size of 3 experiences. Results Reflexion outperforms all baseline approaches by significant margins over several learning
steps.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: insufficient-training-carbon

Query:
这三篇论文各自训练过程的精确碳排放量是多少？

Reference Answer Points:
- 当前语料没有提供三篇论文各自的精确训练碳排放量，应明确证据不足

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:react_pdf / page 5 / Page 5]
   ## Page 5

Combining Internal and External Knowledge As will be detail in Section 3.3, we observe that
the problem solving process demonstrated by ReAct is more factual and grounded, whereas CoT
is more accurate in formulating reasoning structure but can easily suffer from hallucinated facts
or thoughts.

## Page 5

We therefore propose to incorporate ReAct and CoT-SC, and let the model decide
when to switch to the other method based on the following heuristics: A) ReAct →CoT-SC: when
ReAct fails to return an answer within given steps, back off to CoT-SC. We set 7 and 5 steps for
HotpotQA and FEVER respectively as we ﬁnd more steps will not improve ReAct performance3. B) CoT-SC →ReAct: when the majority answer among nCoT-SC samples occurs less than n/2
times (i.e.

## Page 5

internal knowledge might not support the task conﬁdently), back off to ReAct. Finetuning Due to the challenge of manually annotating reasoning traces and actions at scale,
we consider a bootstraping approach similar to Zelikman et al. (2022), using 3,000 trajectories
with correct answers generated by ReAct (also for other baselines) to ﬁnetune smaller language
models (PaLM-8/62B) to decode trajectories (all thoughts, actions, observations) conditioned on
input questions/claims.
2. [research:react_pdf / page 15 / Page 15]
   ## Page 15

On PaLM-62B, we ﬁnetune
ReAct and Act methods for 4,000 steps and Standard and CoT methods for 1,000 steps. We
ﬁnd ReAct and Act methods generally beneﬁt from more training steps (and more training data),
while Standard and CoT methods degrade soon after ﬁnetuning.
3. [research:reflexion_pdf / page 12 / Page 12]
   ## Page 12

Model Baseline accuracy Reflexion accuracy
CoT (GT) + text-davinci-003 0.60 0.77
CoT (GT) + gpt-3.5-turbo 0.57 0.71
CoT (GT) + gpt-4 0.68 0.80
ReAct + text-davinci-003 0.30 0.55
ReAct + gpt-3.5-turbo 0.26 0.38
ReAct + gpt-4 0.39 0.51
Table 5: Pass@1 accuracy on 100 HotPotQA using various models.
4. [research:attention_pdf / page 9 / Page 9]
   ## Page 9

N d model dff h d k dv Pdrop ϵls
train PPL BLEU params
steps (dev) (dev) ×106
base 6 512 2048 8 64 64 0.1 0.1 100K 4.92 25.8 65
(A)
1 512 512 5.29 24.9
4 128 128 5.00 25.5
16 32 32 4.91 25.8
32 16 16 5.01 25.4
(B) 16 5.16 25.1 58
32 5.01 25.4 60
(C)
2 6.11 23.7 36
4 5.19 25.3 50
8 4.88 25.5 80
256 32 32 5.75 24.5 28
1024 128 128 4.66 26.0 168
1024 5.12 25.4 53
4096 4.75 26.2 90
(D)
0.0 5.77 24.6
0.2 4.95 25.5
0.0 4.67 25.3
0.2 5.47 25.7
(E) positional embedding instead of sinusoids 4.92 25.7
big 6 1024 4096 16 0.3 300K 4.33 26.4 213
development set, newstest2013.
5. [research:react_pdf / page 6 / Page 6]
   ## Page 6

In contrast,
ﬁnetuning Standard or CoT is signiﬁcantly worse than ﬁnetuning ReAct or Act for both PaLM-
8/62B, as the former essentially teaches models to memorize (potentially halluincated) knowledge
facts, and the latter teaches models how to (reason and) act to access information from Wikipedia, a
more generalizable skill for knowledge reasoning.
6. [research:react_pdf / page 5 / Page 5]
   ## Page 5

b(Zhu et al., 2021; Lewis et al., 2020)
0 5 10 15 20
#CoT-SC trials
34HotpotQA EM
0 5 10 15 20
#CoT-SC trials
47.5
50.0
52.5
55.0
57.5
60.0
62.5
65.0Fever Acc
Method
CoT-SC -> ReAct
ReAct -> CoT-SC
CoT-SC
ReAct
CoT
Figure 2: PaLM-540B prompting results with respect to
number of CoT-SC samples used. search reformulation (“maybe I can search/look up x instead”), and synthesize the ﬁnal answer (“...so
the answer is x”). See Appendix C for more details.
7. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

Furthermore, ReAct-only, CoT-only, and CoT (GT)-only implementations fail to probabilisti-
cally improve on any tasks, meaning that no failed tasks from the first trial from any of the baseline
approaches were able to be solved in subsequent trials using a temperature of 0.7 In the Reflexion runs,
we allowed the agent to gather experience and retry on failed tasks until it produced 3 consecutive
failed attempts on the particular task.
8. [research:attention_pdf / page 8 / Page 8]
   ## Page 8

Model
BLEU Training Cost (FLOPs)
EN-DE EN-FR EN-DE EN-FR
ByteNet [18] 23.75
Deep-Att + PosUnk [39] 39.2 1.0 · 1020
GNMT + RL [38] 24.6 39.92 2.3 · 1019 1.4 · 1020
ConvS2S [9] 25.16 40.46 9.6 · 1018 1.5 · 1020
MoE [32] 26.03 40.56 2.0 · 1019 1.2 · 1020
Deep-Att + PosUnk Ensemble [39] 40.4 8.0 · 1020
GNMT + RL Ensemble [38] 26.30 41.16 1.8 · 1020 1.1 · 1021
ConvS2S Ensemble [9] 26.36 41.29 7.7 · 1019 1.2 · 1021
Transformer (base model) 27.3 38.1 3.3 · 1018
Transformer (big) 28.4 41.8 2.3 · 1019
Residual Dropout We apply dropout [33] to the output of each sub-layer, before it is added to the
sub-layer input and normalized.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------

## Case: insufficient-2026-production

Query:
ReAct、Reflexion 和 Transformer 在 2026 年全球生产部署中的精确市场份额分别是多少？

Reference Answer Points:
- 当前论文语料不包含 2026 年全球生产部署市场份额，应拒绝编造

Final Answer:
无法基于当前证据可靠生成回答

Retrieved Evidence:
1. [research:reflexion_pdf / page 14 / Page 14]
   ## Page 14

In HotPotQA,
the agent faces a similar WebShop search query task but is more successful as the search space for
Wikipedia articles is more diverse and requires less precise search queries. A common problem for
e-commerce search engines is properly handling ambiguity in natural language search interpretations. Thus, WebShop presents a task that requires very diverse and unique behavior from a Reflexion agent.

## Page 14

0.0 0.5 1.0 1.5 2.0 2.5 3.0
Trial Number
0.10
0.15
0.20
0.25
0.30
0.35
0.40
0.45
0.50Proportion of Solved Environments
WebShop Success Rate
ReAct only
ReAct + Reflexion
Figure 6: Reflexion vs React performance on WebShop across 100 customer shopping requests. ReAct + Reflexion fails to significantly outperform ReAct. C Programming
Programming LLM calls require strict instructions to produce function bodies only, due to the
extensive dialogue training of the LLMs.

## Page 14

A few programming examples are reported below with
instructions highlighted in blue and templates. See the full implementation at https://github. com/noahshinn024/reflexion. C.1 Programming function implementation example (HumanEval Python)
Sample function signature:
1 def minSubArraySum ( nums ):
2 """
3 Given an array of integers nums , find the minimum sum of
any
4 non - empty sub - array of nums . 5 Example
6 minSubArraySum ([2 , 3, 4, 1, 2, 4]) == 1
2. [research:reflexion_pdf / page 5 / Page 5]
   ## Page 5

Further, ReAct + Reflexion
learns to solve additional tasks by learning in 12 consecutive trials. In the ReAct-only approach, we
see that performance increase halts between trials 6 and 7. Analysis A common error in baseline failed AlfWorld trajectories is when an agent thinks that it
has possession of an item but does not actually have the item. The agent proceeds to execute several
actions in a long trajectory and is not able to backtrack its actions to find the mistake. Reflexion
3. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

Reflexion improves search, information retrieval,
and reasoning capabilities on 100 HotPotQA questions. (a) Reflexion ReAct vs Reflexion CoT (b)
Reflexion CoT (GT) for reasoning only (c) Reflexion vs episodic memory ablation. Analysis We perform an ablation experiment to isolate the advantage of the self-reflective step for
reasoning using CoT (GT) as the baseline approach 4.
4. [research:react_pdf / page 8 / Page 8]
   ## Page 8

On
ALFWorld, the bestReAct trial achieves an average success rate of 71%, signiﬁcantly outperforming
the best Act (45%) and BUTLER (37%) trials. In fact, even the worse ReAct trial (48%) beats
the best trial of both methods. Moreover, the advantage of ReAct over Act is consistent across
six controlled trials, with relative performance gain ranging from 33% to 90% and averaging 62%.
5. [research:reflexion_pdf / page 3 / Page 3]
   ## Page 3

We provide a detailed description of each of these
models and subsequently elucidate their collaborative functioning within the Reflexion framework.
6. [research:reflexion_pdf / page 6 / Page 6]
   ## Page 6

0 2 4 6 8 10
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Environments
(a) ALFWorld Success Rate
ReAct only
ReAct + Reflexion (Heuristic)
ReAct + Reflexion (GPT)
0 2 4 6 8 10
Trial Number
0.0
0.1
0.2
0.3
0.4
0.5Proportion of Environments
(a) ALFWorld Success Rate
ReAct only - hallucination
ReAct only - inefficient planning
ReAct + Reflexion - hallucination
ReAct + Reflexion - inefficient planning
Figure 3: (a) AlfWorld performance across 134 tasks showing cumulative proportions of solved tasks
using self-evaluation techniques of (Heuristic) and (GPT) for binary classification.
7. [research:reflexion_pdf / page 2 / Page 2]
   ## Page 2

Across all three types of tasks, we observe Reflexion agents are better decision-
makers, reasoners, and programmers. More concretely, Reflexion agents improve on decision-making
AlfWorld [24] tasks over strong baseline approaches by an absolute 22% in 12 iterative learning
steps, and on reasoning questions in HotPotQA [ 28] by 20%, and Python programming tasks on
HumanEval [6] by as much as 11%.
8. [research:reflexion_pdf / page 7 / Page 7]
   ## Page 7

0 2 4 6
Trial Number
0.2
0.4
0.6
0.8Proportion of Solved Tasks
(a) HotPotQA Success Rate
CoT only
ReAct only
CoT + Reflexion
ReAct + Reflexion
0 1 2 3 4 5 6 7
Trial Number
0.4
0.6
0.8
1.0Proportion of Solved Tasks
(b) HotPotQA CoT (GT)
CoT (GT) only
CoT (GT) + Reflexion
0 1 2 3 4
Trial Number
0.5
0.6
0.7
0.8
0.9
1.0Proportion of Solved Tasks
(c) HotPotQA Episodic Memory
CoT (GT) only
CoT (GT) EPM
CoT (GT) EPM + Reflexion
Figure 4: Chain-of-Thought (CoT) and ReAct.

Claims:

Answer Correctness:
[ ] FULL
[ ] PARTIAL
[ ] INCORRECT

Context Resolution:
[ ] PASS
[ ] FAIL
[ ] N/A

Cross-session Memory Recall:
[ ] PASS
[ ] FAIL
[ ] N/A

Insufficient-evidence Handling:
[ ] PASS
[ ] FAIL
[ ] N/A

Human Notes:

--------------------------------------------------
