# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import json
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from loguru import logger


class Proposal:
    def __init__(self):
        self.actions = []

    def asdict(self) -> Dict[str, Any]:
        return {"actions": self.actions}

    def set_constitution(self, constitution_files: List[str]):
        constitution = []
        for file in constitution_files:
            with open(file, "r", encoding="utf-8") as f:
                constitution.append(f.read())
        action = {
            "name": "set_constitution",
            "args": {
                "constitution": "\n".join(constitution),
            },
        }
        self.actions.append(action)
        return self

    def set_public_prefix(self, public_prefix: str):
        action = {
            "name": "set_public_prefix",
            "args": {
                "public_prefix": public_prefix,
            },
        }
        self.actions.append(action)
        return self

    def remove_public_prefix(self, public_prefix: str):
        action = {
            "name": "remove_public_prefix",
            "args": {
                "public_prefix": public_prefix,
            },
        }
        self.actions.append(action)
        return self


@dataclass
class ProposalResponse:
    ballot_count: int
    proposal_id: str
    proposer_id: str
    state: str
    votes: Dict[str, bool] = field(default_factory=dict)


@dataclass
class CCFError:
    code: str
    message: str


class Client:
    def __init__(
        self,
        address: str,
        cacert: str,
        signing_key: str,
        signing_cert: str,
    ):
        self.address = address
        self.cacert = cacert
        self.signing_key = signing_key
        self.signing_cert = signing_cert

    def run(
        self, gov_msg_type: str, content_file: str, proposal_id: Optional[str] = None
    ) -> ProposalResponse:
        path = "/gov/proposals"
        cose_sign1_cmd = f"ccf_cose_sign1 --ccf-gov-msg-type {gov_msg_type} --signing-key {self.signing_key} --signing-cert {self.signing_cert} --content {content_file}"
        if proposal_id:
            cose_sign1_cmd += f" --ccf-gov-msg-proposal_id {proposal_id}"
            path += f"/{proposal_id}/ballots"

        curl_cmd = f"curl https://{self.address}{path} --cacert {self.cacert} --data-binary @- -H 'content-type: application/cose'"
        cmd = f"{cose_sign1_cmd} | {curl_cmd}"
        logger.debug("Running: {}", cmd)

        res = subprocess.run(cmd, shell=True, check=True, capture_output=True)
        logger.debug("Stdout: {}", res.stdout)
        logger.debug("Stderr: {}", res.stderr)
        ret = res.stdout.decode("utf-8")
        ret_json = json.loads(ret)
        if "error" in ret_json:
            ccf_error = CCFError(**ret_json["error"])
            raise Exception(ccf_error)
        return ProposalResponse(**ret_json)

    def propose(self, proposals: Proposal) -> ProposalResponse:
        proposal_dict = proposals.asdict()
        proposal_json = json.dumps(proposal_dict)
        with open("proposal_content.json", "w", encoding="utf-8") as f:
            f.write(proposal_json)
        res = self.run("proposal", "proposal_content.json")
        logger.debug("Created proposal with id {}", res.proposal_id)
        return res

    def accept(self, proposal_id: str):
        accept = {
            "ballot": "export function vote (proposal, proposerId) { return true }"
        }
        accept_json = json.dumps(accept)
        with open("proposal_content.json", "w", encoding="utf-8") as f:
            f.write(accept_json)
        res = self.run("ballot", "proposal_content.json", proposal_id=proposal_id)
        logger.debug("Success: proposal state is {}", res.state)
        return res


if __name__ == "__main__":
    proposal = Proposal()
    proposal.set_constitution(
        [
            "constitution/actions.js",
            "constitution/apply.js",
            "constitution/resolve.js",
            "constitution/validate.js",
        ]
    )
    client = Client(
        "127.0.0.1:8000",
        "workspace/sandbox_common/service_cert.pem",
        "workspace/sandbox_common/member0_privk.pem",
        "workspace/sandbox_common/member0_cert.pem",
    )
    res = client.propose(proposal)
    client.accept(res.proposal_id)

    proposal = Proposal()
    proposal.remove_public_prefix("test")
    res = client.propose(proposal)
    client.accept(res.proposal_id)

    proposal = Proposal()
    proposal.set_public_prefix("test")
    res = client.propose(proposal)
    client.accept(res.proposal_id)
