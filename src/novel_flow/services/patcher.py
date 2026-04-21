from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from novel_flow.exceptions import PatchExecutionError
from novel_flow.models.schemas import BlockPatchVersion, BookDocument, PatchInstruction, PatchOperation, TextBlock


class PatchExecutor:
    def apply(self, book: BookDocument, instruction: PatchInstruction) -> tuple[BookDocument, BlockPatchVersion]:
        book_copy = deepcopy(book)

        for volume in book_copy.volumes:
            for chapter in volume.chapters:
                for scene in chapter.scenes:
                    for index, block in enumerate(scene.blocks):
                        if block.id != instruction.target_block_id:
                            continue
                        before_block = deepcopy(block)
                        updated_text = self._apply_operation(block.text, instruction)
                        scene.blocks[index] = TextBlock(
                            id=block.id,
                            text=updated_text,
                            purpose=block.purpose,
                            metadata={**block.metadata, "last_patch_id": instruction.patch_id},
                        )
                        if getattr(chapter, "content_blocks", None):
                            for block_index, content_block in enumerate(chapter.content_blocks):
                                if content_block.block_id != instruction.target_block_id:
                                    continue
                                chapter.content_blocks[block_index] = content_block.model_copy(
                                    update={
                                        "text": updated_text,
                                        "status": "committed",
                                        "version": max(int(content_block.version), 1) + 1,
                                    }
                                )
                                chapter.final_text = ""
                                chapter.is_finalized = False
                                chapter.final_version = max(int(chapter.final_version), 0) + 1
                                break
                        after_block = deepcopy(scene.blocks[index])
                        book_copy.updated_at = datetime.now(timezone.utc)
                        version = BlockPatchVersion(
                            version_id=f"ver_{uuid4().hex[:12]}",
                            book_id=book_copy.id,
                            block_id=instruction.target_block_id,
                            patch_id=instruction.patch_id,
                            before_block=before_block,
                            after_block=after_block,
                            instruction=instruction,
                        )
                        return book_copy, version

        raise PatchExecutionError(f"Block not found: {instruction.target_block_id}")

    @staticmethod
    def _apply_operation(text: str, instruction: PatchInstruction) -> str:
        if instruction.operation == PatchOperation.REPLACE:
            return instruction.content
        if instruction.operation == PatchOperation.APPEND:
            return text.rstrip() + "\n" + instruction.content.strip()
        if instruction.operation == PatchOperation.PREPEND:
            return instruction.content.strip() + "\n" + text.lstrip()
        raise PatchExecutionError(f"Unsupported patch operation: {instruction.operation}")
