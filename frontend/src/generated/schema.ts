// @ts-nocheck
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */

export type Scalars = {
    String: string,
    ID: string,
    Boolean: boolean,
    Int: number,
}

export interface AgentDoneEvent {
    agentId: Scalars['String']
    node: Scalars['String']
    __typename: 'AgentDoneEvent'
}

export interface AgentSpawnedEvent {
    agentId: Scalars['String']
    agentName: Scalars['String']
    node: Scalars['String']
    __typename: 'AgentSpawnedEvent'
}

export interface AgentTokenEvent {
    agentId: Scalars['String']
    token: Scalars['String']
    __typename: 'AgentTokenEvent'
}

export interface AgentToolCallEvent {
    agentId: Scalars['String']
    toolName: Scalars['String']
    inputPreview: Scalars['String']
    __typename: 'AgentToolCallEvent'
}

export interface AgentToolResultEvent {
    agentId: Scalars['String']
    toolName: Scalars['String']
    resultSummary: Scalars['String']
    __typename: 'AgentToolResultEvent'
}

export interface CreateJobResult {
    jobId: Scalars['ID']
    status: Scalars['String']
    __typename: 'CreateJobResult'
}

export interface DeleteTokenResult {
    ok: Scalars['Boolean']
    __typename: 'DeleteTokenResult'
}

export interface GraphInterruptEvent {
    question: Scalars['String']
    context: Scalars['String']
    __typename: 'GraphInterruptEvent'
}

export interface GraphNodeCompleteEvent {
    node: Scalars['String']
    step: (Scalars['Int'] | null)
    __typename: 'GraphNodeCompleteEvent'
}

export interface Job {
    jobId: Scalars['ID']
    status: Scalars['String']
    issueUrl: Scalars['String']
    issueTitle: Scalars['String']
    repository: Scalars['String']
    langsmithUrl: Scalars['String']
    awaitingHuman: Scalars['Boolean']
    currentNode: Scalars['String']
    createdAt: Scalars['String']
    pendingQuestion: Scalars['String']
    pendingQuestionContext: Scalars['String']
    githubCommentUrl: Scalars['String']
    severity: Scalars['String']
    recommendedFix: Scalars['String']
    githubComment: Scalars['String']
    relevantFiles: Scalars['String'][]
    ticketTitle: Scalars['String']
    __typename: 'Job'
}

export interface JobActionResult {
    status: Scalars['String']
    jobId: Scalars['ID']
    __typename: 'JobActionResult'
}

export interface JobDoneEvent {
    Empty: (Scalars['Boolean'] | null)
    __typename: 'JobDoneEvent'
}

export type JobEvent = (AgentSpawnedEvent | AgentTokenEvent | OutputTokenEvent | AgentToolCallEvent | AgentToolResultEvent | AgentDoneEvent | OutputSectionDoneEvent | GraphNodeCompleteEvent | GraphInterruptEvent | JobDoneEvent | JobFailedEvent | JobKilledEvent | JobTimedOutEvent | JobSnapshotEvent) & { __isUnion?: true }

export interface JobFailedEvent {
    error: Scalars['String']
    __typename: 'JobFailedEvent'
}

export interface JobKilledEvent {
    Empty: (Scalars['Boolean'] | null)
    __typename: 'JobKilledEvent'
}

export interface JobSnapshotEvent {
    status: Scalars['String']
    currentNode: Scalars['String']
    awaitingHuman: Scalars['Boolean']
    pendingQuestion: Scalars['String']
    pendingQuestionContext: Scalars['String']
    __typename: 'JobSnapshotEvent'
}

export interface JobTimedOutEvent {
    Empty: (Scalars['Boolean'] | null)
    __typename: 'JobTimedOutEvent'
}

export interface LogoutResult {
    ok: Scalars['Boolean']
    __typename: 'LogoutResult'
}

export interface Mutation {
    createJob: CreateJobResult
    killJob: JobActionResult
    answerJob: JobActionResult
    pauseJob: JobActionResult
    resumeJob: JobActionResult
    redirectJob: JobActionResult
    postComment: PostCommentResult
    logout: LogoutResult
    deleteGithubToken: DeleteTokenResult
    __typename: 'Mutation'
}

export interface OutputSectionDoneEvent {
    section: Scalars['String']
    __typename: 'OutputSectionDoneEvent'
}

export interface OutputTokenEvent {
    token: Scalars['String']
    section: Scalars['String']
    __typename: 'OutputTokenEvent'
}

export interface PostCommentResult {
    ok: Scalars['Boolean']
    commentUrl: Scalars['String']
    __typename: 'PostCommentResult'
}

export interface Query {
    me: UserInfo
    job: Job
    jobs: Job[]
    __typename: 'Query'
}

export interface Subscription {
    jobEvents: JobEvent
    __typename: 'Subscription'
}

export interface UserInfo {
    githubId: Scalars['String']
    githubLogin: Scalars['String']
    avatarUrl: Scalars['String']
    __typename: 'UserInfo'
}

export interface AgentDoneEventGenqlSelection{
    agentId?: boolean | number
    node?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface AgentSpawnedEventGenqlSelection{
    agentId?: boolean | number
    agentName?: boolean | number
    node?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface AgentTokenEventGenqlSelection{
    agentId?: boolean | number
    token?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface AgentToolCallEventGenqlSelection{
    agentId?: boolean | number
    toolName?: boolean | number
    inputPreview?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface AgentToolResultEventGenqlSelection{
    agentId?: boolean | number
    toolName?: boolean | number
    resultSummary?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface CreateJobInput {issueUrl: Scalars['String'],supervisorNotes?: Scalars['String']}

export interface CreateJobResultGenqlSelection{
    jobId?: boolean | number
    status?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface DeleteTokenResultGenqlSelection{
    ok?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface GraphInterruptEventGenqlSelection{
    question?: boolean | number
    context?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface GraphNodeCompleteEventGenqlSelection{
    node?: boolean | number
    step?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobGenqlSelection{
    jobId?: boolean | number
    status?: boolean | number
    issueUrl?: boolean | number
    issueTitle?: boolean | number
    repository?: boolean | number
    langsmithUrl?: boolean | number
    awaitingHuman?: boolean | number
    currentNode?: boolean | number
    createdAt?: boolean | number
    pendingQuestion?: boolean | number
    pendingQuestionContext?: boolean | number
    githubCommentUrl?: boolean | number
    severity?: boolean | number
    recommendedFix?: boolean | number
    githubComment?: boolean | number
    relevantFiles?: boolean | number
    ticketTitle?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobActionResultGenqlSelection{
    status?: boolean | number
    jobId?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobDoneEventGenqlSelection{
    Empty?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobEventGenqlSelection{
    on_AgentSpawnedEvent?:AgentSpawnedEventGenqlSelection,
    on_AgentTokenEvent?:AgentTokenEventGenqlSelection,
    on_OutputTokenEvent?:OutputTokenEventGenqlSelection,
    on_AgentToolCallEvent?:AgentToolCallEventGenqlSelection,
    on_AgentToolResultEvent?:AgentToolResultEventGenqlSelection,
    on_AgentDoneEvent?:AgentDoneEventGenqlSelection,
    on_OutputSectionDoneEvent?:OutputSectionDoneEventGenqlSelection,
    on_GraphNodeCompleteEvent?:GraphNodeCompleteEventGenqlSelection,
    on_GraphInterruptEvent?:GraphInterruptEventGenqlSelection,
    on_JobDoneEvent?:JobDoneEventGenqlSelection,
    on_JobFailedEvent?:JobFailedEventGenqlSelection,
    on_JobKilledEvent?:JobKilledEventGenqlSelection,
    on_JobTimedOutEvent?:JobTimedOutEventGenqlSelection,
    on_JobSnapshotEvent?:JobSnapshotEventGenqlSelection,
    __typename?: boolean | number
}

export interface JobFailedEventGenqlSelection{
    error?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobKilledEventGenqlSelection{
    Empty?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobSnapshotEventGenqlSelection{
    status?: boolean | number
    currentNode?: boolean | number
    awaitingHuman?: boolean | number
    pendingQuestion?: boolean | number
    pendingQuestionContext?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface JobTimedOutEventGenqlSelection{
    Empty?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface LogoutResultGenqlSelection{
    ok?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface MutationGenqlSelection{
    createJob?: (CreateJobResultGenqlSelection & { __args: {input: CreateJobInput} })
    killJob?: (JobActionResultGenqlSelection & { __args: {jobId: Scalars['ID']} })
    answerJob?: (JobActionResultGenqlSelection & { __args: {jobId: Scalars['ID'], answer: Scalars['String']} })
    pauseJob?: (JobActionResultGenqlSelection & { __args: {jobId: Scalars['ID']} })
    resumeJob?: (JobActionResultGenqlSelection & { __args: {jobId: Scalars['ID']} })
    redirectJob?: (JobActionResultGenqlSelection & { __args: {jobId: Scalars['ID'], instruction: Scalars['String']} })
    postComment?: (PostCommentResultGenqlSelection & { __args: {jobId: Scalars['ID'], comment?: (Scalars['String'] | null)} })
    logout?: LogoutResultGenqlSelection
    deleteGithubToken?: DeleteTokenResultGenqlSelection
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface OutputSectionDoneEventGenqlSelection{
    section?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface OutputTokenEventGenqlSelection{
    token?: boolean | number
    section?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface PostCommentResultGenqlSelection{
    ok?: boolean | number
    commentUrl?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface QueryGenqlSelection{
    me?: UserInfoGenqlSelection
    job?: (JobGenqlSelection & { __args: {jobId: Scalars['ID']} })
    jobs?: JobGenqlSelection
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface SubscriptionGenqlSelection{
    jobEvents?: (JobEventGenqlSelection & { __args: {jobId: Scalars['ID']} })
    __typename?: boolean | number
    __scalar?: boolean | number
}

export interface UserInfoGenqlSelection{
    githubId?: boolean | number
    githubLogin?: boolean | number
    avatarUrl?: boolean | number
    __typename?: boolean | number
    __scalar?: boolean | number
}


    const AgentDoneEvent_possibleTypes: string[] = ['AgentDoneEvent']
    export const isAgentDoneEvent = (obj?: { __typename?: any } | null): obj is AgentDoneEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isAgentDoneEvent"')
      return AgentDoneEvent_possibleTypes.includes(obj.__typename)
    }
    


    const AgentSpawnedEvent_possibleTypes: string[] = ['AgentSpawnedEvent']
    export const isAgentSpawnedEvent = (obj?: { __typename?: any } | null): obj is AgentSpawnedEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isAgentSpawnedEvent"')
      return AgentSpawnedEvent_possibleTypes.includes(obj.__typename)
    }
    


    const AgentTokenEvent_possibleTypes: string[] = ['AgentTokenEvent']
    export const isAgentTokenEvent = (obj?: { __typename?: any } | null): obj is AgentTokenEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isAgentTokenEvent"')
      return AgentTokenEvent_possibleTypes.includes(obj.__typename)
    }
    


    const AgentToolCallEvent_possibleTypes: string[] = ['AgentToolCallEvent']
    export const isAgentToolCallEvent = (obj?: { __typename?: any } | null): obj is AgentToolCallEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isAgentToolCallEvent"')
      return AgentToolCallEvent_possibleTypes.includes(obj.__typename)
    }
    


    const AgentToolResultEvent_possibleTypes: string[] = ['AgentToolResultEvent']
    export const isAgentToolResultEvent = (obj?: { __typename?: any } | null): obj is AgentToolResultEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isAgentToolResultEvent"')
      return AgentToolResultEvent_possibleTypes.includes(obj.__typename)
    }
    


    const CreateJobResult_possibleTypes: string[] = ['CreateJobResult']
    export const isCreateJobResult = (obj?: { __typename?: any } | null): obj is CreateJobResult => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isCreateJobResult"')
      return CreateJobResult_possibleTypes.includes(obj.__typename)
    }
    


    const DeleteTokenResult_possibleTypes: string[] = ['DeleteTokenResult']
    export const isDeleteTokenResult = (obj?: { __typename?: any } | null): obj is DeleteTokenResult => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isDeleteTokenResult"')
      return DeleteTokenResult_possibleTypes.includes(obj.__typename)
    }
    


    const GraphInterruptEvent_possibleTypes: string[] = ['GraphInterruptEvent']
    export const isGraphInterruptEvent = (obj?: { __typename?: any } | null): obj is GraphInterruptEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isGraphInterruptEvent"')
      return GraphInterruptEvent_possibleTypes.includes(obj.__typename)
    }
    


    const GraphNodeCompleteEvent_possibleTypes: string[] = ['GraphNodeCompleteEvent']
    export const isGraphNodeCompleteEvent = (obj?: { __typename?: any } | null): obj is GraphNodeCompleteEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isGraphNodeCompleteEvent"')
      return GraphNodeCompleteEvent_possibleTypes.includes(obj.__typename)
    }
    


    const Job_possibleTypes: string[] = ['Job']
    export const isJob = (obj?: { __typename?: any } | null): obj is Job => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJob"')
      return Job_possibleTypes.includes(obj.__typename)
    }
    


    const JobActionResult_possibleTypes: string[] = ['JobActionResult']
    export const isJobActionResult = (obj?: { __typename?: any } | null): obj is JobActionResult => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobActionResult"')
      return JobActionResult_possibleTypes.includes(obj.__typename)
    }
    


    const JobDoneEvent_possibleTypes: string[] = ['JobDoneEvent']
    export const isJobDoneEvent = (obj?: { __typename?: any } | null): obj is JobDoneEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobDoneEvent"')
      return JobDoneEvent_possibleTypes.includes(obj.__typename)
    }
    


    const JobEvent_possibleTypes: string[] = ['AgentSpawnedEvent','AgentTokenEvent','OutputTokenEvent','AgentToolCallEvent','AgentToolResultEvent','AgentDoneEvent','OutputSectionDoneEvent','GraphNodeCompleteEvent','GraphInterruptEvent','JobDoneEvent','JobFailedEvent','JobKilledEvent','JobTimedOutEvent','JobSnapshotEvent']
    export const isJobEvent = (obj?: { __typename?: any } | null): obj is JobEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobEvent"')
      return JobEvent_possibleTypes.includes(obj.__typename)
    }
    


    const JobFailedEvent_possibleTypes: string[] = ['JobFailedEvent']
    export const isJobFailedEvent = (obj?: { __typename?: any } | null): obj is JobFailedEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobFailedEvent"')
      return JobFailedEvent_possibleTypes.includes(obj.__typename)
    }
    


    const JobKilledEvent_possibleTypes: string[] = ['JobKilledEvent']
    export const isJobKilledEvent = (obj?: { __typename?: any } | null): obj is JobKilledEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobKilledEvent"')
      return JobKilledEvent_possibleTypes.includes(obj.__typename)
    }
    


    const JobSnapshotEvent_possibleTypes: string[] = ['JobSnapshotEvent']
    export const isJobSnapshotEvent = (obj?: { __typename?: any } | null): obj is JobSnapshotEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobSnapshotEvent"')
      return JobSnapshotEvent_possibleTypes.includes(obj.__typename)
    }
    


    const JobTimedOutEvent_possibleTypes: string[] = ['JobTimedOutEvent']
    export const isJobTimedOutEvent = (obj?: { __typename?: any } | null): obj is JobTimedOutEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isJobTimedOutEvent"')
      return JobTimedOutEvent_possibleTypes.includes(obj.__typename)
    }
    


    const LogoutResult_possibleTypes: string[] = ['LogoutResult']
    export const isLogoutResult = (obj?: { __typename?: any } | null): obj is LogoutResult => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isLogoutResult"')
      return LogoutResult_possibleTypes.includes(obj.__typename)
    }
    


    const Mutation_possibleTypes: string[] = ['Mutation']
    export const isMutation = (obj?: { __typename?: any } | null): obj is Mutation => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isMutation"')
      return Mutation_possibleTypes.includes(obj.__typename)
    }
    


    const OutputSectionDoneEvent_possibleTypes: string[] = ['OutputSectionDoneEvent']
    export const isOutputSectionDoneEvent = (obj?: { __typename?: any } | null): obj is OutputSectionDoneEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isOutputSectionDoneEvent"')
      return OutputSectionDoneEvent_possibleTypes.includes(obj.__typename)
    }
    


    const OutputTokenEvent_possibleTypes: string[] = ['OutputTokenEvent']
    export const isOutputTokenEvent = (obj?: { __typename?: any } | null): obj is OutputTokenEvent => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isOutputTokenEvent"')
      return OutputTokenEvent_possibleTypes.includes(obj.__typename)
    }
    


    const PostCommentResult_possibleTypes: string[] = ['PostCommentResult']
    export const isPostCommentResult = (obj?: { __typename?: any } | null): obj is PostCommentResult => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isPostCommentResult"')
      return PostCommentResult_possibleTypes.includes(obj.__typename)
    }
    


    const Query_possibleTypes: string[] = ['Query']
    export const isQuery = (obj?: { __typename?: any } | null): obj is Query => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isQuery"')
      return Query_possibleTypes.includes(obj.__typename)
    }
    


    const Subscription_possibleTypes: string[] = ['Subscription']
    export const isSubscription = (obj?: { __typename?: any } | null): obj is Subscription => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isSubscription"')
      return Subscription_possibleTypes.includes(obj.__typename)
    }
    


    const UserInfo_possibleTypes: string[] = ['UserInfo']
    export const isUserInfo = (obj?: { __typename?: any } | null): obj is UserInfo => {
      if (!obj?.__typename) throw new Error('__typename is missing in "isUserInfo"')
      return UserInfo_possibleTypes.includes(obj.__typename)
    }
    