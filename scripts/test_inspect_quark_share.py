"""Contract tests for evidence, traversal limits, and safe public-share errors."""

import json
from unittest import TestCase, main
from unittest.mock import patch
from urllib.error import HTTPError

import inspect_quark_share as probe

SHARE = "https://pan.quark.cn/s/abcdef123456"


def video(name="loop.mp4", width=3840, height=2160):
    return {"file_name": name, "video_width": width, "video_height": height,
            "fps": 60, "duration": 20, "size": 1234, "updated_at": 1794632400000}


def directory(fid, name):
    return {"file_name": name, "dir": True, "fid": fid}


def public_api(pages):
    def respond(endpoint, query, body=None, timeout=15):
        if endpoint.endswith("/token"):
            return {"data": {"stoken": "EPHEMERAL_TEST_TOKEN"}}
        key = (query["pdir_fid"], query["_page"])
        answer = pages[key]
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, dict):
            return answer
        return {"data": {"list": answer}}
    return respond


class QuarkShareEvidenceTests(TestCase):
    def inspect(self, pages, **kwargs):
        with patch.object(probe, "request_json", side_effect=public_api(pages)):
            return probe.inspect_share(SHARE, **kwargs)

    def test_only_actual_video_entries_with_sufficient_dimensions_qualify(self):
        result = self.inspect({("0", 1): [
            video(),
            video("near-4k.mp4", 3838, 2160),
            video("short-height.mp4", 3840, 2156),
            video("portrait.mp4", 2160, 3840),
            {"file_name": "label-4K.mp4"},
            video("image-4K.png"),
            video("unopened.zip"),
        ]})
        self.assertEqual([item["file_name"] for item in result["eligible_media"]], ["loop.mp4"])
        self.assertEqual(result["evidence_level"], "cloud_metadata")
        self.assertEqual(result["download_status"], "not_attempted")
        self.assertTrue(result["listing_complete"])
        self.assertNotIn("EPHEMERAL_TEST_TOKEN", json.dumps(result))
        self.assertEqual(result["entries"][4]["resolution_status"], "unknown")
        self.assertTrue(result["entries"][0]["cloud_modified_at"].endswith("+00:00"))

    def test_pagination_reads_beyond_first_page(self):
        result = self.inspect({
            ("0", 1): [video(f"{i}.mp4") for i in range(100)],
            ("0", 2): [video("last.mp4")],
        })
        self.assertEqual(len(result["eligible_media"]), 101)
        self.assertTrue(result["listing_complete"])

    def test_short_page_uses_reported_folder_total(self):
        result = self.inspect({
            ("0", 1): {"metadata": {"_total": 2}, "data": {"list": [video()]}},
            ("0", 2): {"metadata": {"_total": 2}, "data": {"list": [video("last.mp4")]}},
        })
        self.assertEqual([item["file_name"] for item in result["eligible_media"]], ["loop.mp4", "last.mp4"])
        self.assertTrue(result["listing_complete"])

    def test_empty_page_before_folder_total_keeps_partial_results(self):
        result = self.inspect({
            ("0", 1): {"metadata": {"_total": 2}, "data": {"list": [video()]}},
            ("0", 2): [],
        })
        self.assertEqual([item["file_name"] for item in result["eligible_media"]], ["loop.mp4"])
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["listing_complete"])
        self.assertEqual(result["errors"], [{"path": "", "reason": "incomplete_listing"}])

    def test_entry_limit_does_not_claim_full_search(self):
        result = self.inspect({("0", 1): [video(f"{i}.mp4") for i in range(5)]}, max_entries=2)
        self.assertEqual(result["entries_scanned"], 2)
        self.assertEqual(result["status"], "partial")
        self.assertFalse(result["listing_complete"])
        self.assertEqual(result["unvisited_folders"][0]["reason"], "entry_limit")

    def test_depth_limit_exposes_folder_for_targeted_follow_up(self):
        pages = {("0", 1): [directory("public-folder", "角色")],
                 ("public-folder", 1): [video()]}
        root = self.inspect(pages, max_depth=0)
        self.assertEqual(root["eligible_media"], [])
        self.assertFalse(root["listing_complete"])
        self.assertEqual(root["unvisited_folders"][0]["folder_id"], "public-folder")
        target = self.inspect(pages, folder_id="public-folder", max_depth=0)
        self.assertEqual(target["eligible_media"][0]["relative_path"], "loop.mp4")
        self.assertTrue(target["listing_complete"])
        recursive = self.inspect(pages)
        self.assertEqual(recursive["eligible_media"][0]["relative_path"], "角色/loop.mp4")

    def test_child_failure_keeps_successful_evidence_without_calling_link_expired(self):
        result = self.inspect({
            ("0", 1): [video(), directory("child", "未读目录")],
            ("child", 1): probe.ShareReadError("http_error_403"),
        })
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["eligible_media"]), 1)
        self.assertFalse(result["listing_complete"])
        self.assertEqual(result["errors"], [{"path": "未读目录", "reason": "http_error_403"}])

    def test_invalid_token_response_is_structured_unavailable(self):
        for data in [None, [], {"stoken": ""}]:
            with self.subTest(data=data), patch.object(probe, "request_json", return_value={"data": data}):
                result = probe.inspect_share(SHARE)
                self.assertEqual(result["status"], "unavailable")
                self.assertEqual(result["evidence_level"], "lead")
                self.assertEqual(result["errors"][0]["reason"], "missing_share_token")

    def test_http_error_does_not_expose_request_url_or_token(self):
        failing = HTTPError("https://example.invalid/?stoken=SECRET", 429, "blocked", {}, None)
        with patch.object(probe.request, "urlopen", side_effect=failing):
            with self.assertRaises(probe.ShareReadError) as failure:
                probe.request_json("/share/sharepage/detail", {"stoken": "SECRET"})
        self.assertEqual(str(failure.exception), "http_error_429")
        self.assertNotIn("SECRET", str(failure.exception))

    def test_share_identifiers_are_canonicalized_and_external_hosts_rejected(self):
        self.assertEqual(probe.share_id(SHARE + "#/list/share"), "abcdef123456")
        for invalid in ["http://pan.quark.cn/s/abcdef123456",
                        "https://example.org/s/abcdef123456",
                        "https://pan.quark.cn/not-a-share/abcdef123456"]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                probe.share_id(invalid)


if __name__ == "__main__":
    main()
