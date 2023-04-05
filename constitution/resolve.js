// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

export function resolve(proposal, proposerId, votes) {
  const memberVoteCount = votes.filter((v) => v.vote).length;

  let activeMemberCount = 0;
  ccf.kv["public:ccf.gov.members.info"].forEach((v) => {
    const info = ccf.bufToJsonCompatible(v);
    if (info.status === "Active") {
      activeMemberCount++;
    }
  });

  // A single member can accept a proposal.
  if (memberVoteCount > 0 && activeMemberCount > 0) {
    return "Accepted";
  }

  return "Open";
}
