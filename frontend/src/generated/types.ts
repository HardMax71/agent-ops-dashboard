export default {
    "scalars": [
        1,
        8,
        10,
        13
    ],
    "types": {
        "AgentDoneEvent": {
            "agentId": [
                1
            ],
            "node": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "String": {},
        "AgentSpawnedEvent": {
            "agentId": [
                1
            ],
            "agentName": [
                1
            ],
            "node": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "AgentTokenEvent": {
            "agentId": [
                1
            ],
            "token": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "AgentToolCallEvent": {
            "agentId": [
                1
            ],
            "toolName": [
                1
            ],
            "inputPreview": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "AgentToolResultEvent": {
            "agentId": [
                1
            ],
            "toolName": [
                1
            ],
            "resultSummary": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "CreateJobInput": {
            "issueUrl": [
                1
            ],
            "supervisorNotes": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "CreateJobResult": {
            "jobId": [
                8
            ],
            "status": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "ID": {},
        "DeleteTokenResult": {
            "ok": [
                10
            ],
            "__typename": [
                1
            ]
        },
        "Boolean": {},
        "GraphInterruptEvent": {
            "question": [
                1
            ],
            "context": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "GraphNodeCompleteEvent": {
            "node": [
                1
            ],
            "step": [
                13
            ],
            "__typename": [
                1
            ]
        },
        "Int": {},
        "Job": {
            "jobId": [
                8
            ],
            "status": [
                1
            ],
            "issueUrl": [
                1
            ],
            "issueTitle": [
                1
            ],
            "repository": [
                1
            ],
            "langsmithUrl": [
                1
            ],
            "awaitingHuman": [
                10
            ],
            "currentNode": [
                1
            ],
            "createdAt": [
                1
            ],
            "githubCommentUrl": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "JobActionResult": {
            "status": [
                1
            ],
            "jobId": [
                8
            ],
            "__typename": [
                1
            ]
        },
        "JobDoneEvent": {
            "Empty": [
                10
            ],
            "__typename": [
                1
            ]
        },
        "JobEvent": {
            "on_AgentSpawnedEvent": [
                2
            ],
            "on_AgentTokenEvent": [
                3
            ],
            "on_OutputTokenEvent": [
                24
            ],
            "on_AgentToolCallEvent": [
                4
            ],
            "on_AgentToolResultEvent": [
                5
            ],
            "on_AgentDoneEvent": [
                0
            ],
            "on_OutputSectionDoneEvent": [
                23
            ],
            "on_GraphNodeCompleteEvent": [
                12
            ],
            "on_GraphInterruptEvent": [
                11
            ],
            "on_JobDoneEvent": [
                16
            ],
            "on_JobFailedEvent": [
                18
            ],
            "on_JobKilledEvent": [
                19
            ],
            "on_JobTimedOutEvent": [
                20
            ],
            "__typename": [
                1
            ]
        },
        "JobFailedEvent": {
            "error": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "JobKilledEvent": {
            "Empty": [
                10
            ],
            "__typename": [
                1
            ]
        },
        "JobTimedOutEvent": {
            "Empty": [
                10
            ],
            "__typename": [
                1
            ]
        },
        "LogoutResult": {
            "ok": [
                10
            ],
            "__typename": [
                1
            ]
        },
        "Mutation": {
            "createJob": [
                7,
                {
                    "input": [
                        6,
                        "CreateJobInput!"
                    ]
                }
            ],
            "killJob": [
                15,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "answerJob": [
                15,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ],
                    "answer": [
                        1,
                        "String!"
                    ]
                }
            ],
            "pauseJob": [
                15,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "resumeJob": [
                15,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "redirectJob": [
                15,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ],
                    "instruction": [
                        1,
                        "String!"
                    ]
                }
            ],
            "postComment": [
                25,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "logout": [
                21
            ],
            "deleteGithubToken": [
                9
            ],
            "__typename": [
                1
            ]
        },
        "OutputSectionDoneEvent": {
            "section": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "OutputTokenEvent": {
            "token": [
                1
            ],
            "section": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "PostCommentResult": {
            "ok": [
                10
            ],
            "commentUrl": [
                1
            ],
            "__typename": [
                1
            ]
        },
        "Query": {
            "me": [
                28
            ],
            "job": [
                14,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "jobs": [
                14
            ],
            "__typename": [
                1
            ]
        },
        "Subscription": {
            "jobEvents": [
                17,
                {
                    "jobId": [
                        8,
                        "ID!"
                    ]
                }
            ],
            "__typename": [
                1
            ]
        },
        "UserInfo": {
            "githubId": [
                1
            ],
            "githubLogin": [
                1
            ],
            "avatarUrl": [
                1
            ],
            "__typename": [
                1
            ]
        }
    }
}