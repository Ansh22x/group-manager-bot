import io
import os
import logging
from pypdf import PdfReader
from database import LoreRepository

logger = logging.getLogger(__name__)

class DocumentRAGService:
    def __init__(self, ai_agent):
        self.ai_agent = ai_agent
        self.lore_repo = LoreRepository()

    def extract_text(self, file_bytes: bytearray, file_name: str) -> str:
        ext = os.path.splitext(file_name)[1].lower()
        text = ""
        
        if ext in ['.txt', '.md']:
            text = file_bytes.decode('utf-8', errors='ignore')
        elif ext == '.pdf':
            try:
                pdf_file = io.BytesIO(file_bytes)
                reader = PdfReader(pdf_file)
                pages_text = []
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        pages_text.append(t)
                text = "\n".join(pages_text)
            except Exception as e:
                logger.error(f"DocumentRAGService: Error reading PDF: {e}")
                raise ValueError(f"Could not parse PDF file: {e}")
        elif ext == '.json':
            try:
                import json
                data = json.loads(file_bytes.decode('utf-8', errors='ignore'))
                text = json.dumps(data, indent=2)
            except Exception as e:
                logger.error(f"DocumentRAGService: Error parsing JSON: {e}")
                raise ValueError(f"Could not parse JSON file: {e}")
        else:
            raise ValueError("Unsupported file format! Please send a .txt, .pdf, or .md document.")
            
        return text

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> list:
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            if end < len(text):
                # Try to cut at a word boundary within the overlap range
                last_boundary = text.rfind(' ', end - 20, end)
                if last_boundary != -1 and last_boundary > start:
                    end = last_boundary
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start = end - overlap if end < len(text) else len(text)
        return chunks

    async def learn_document(self, chat_id: int, file_bytes: bytearray, file_name: str) -> int:
        """Extracts text, chunks it, generates embeddings, and saves to bot_lore table under custom_chat_id namespace"""
        text = self.extract_text(file_bytes, file_name)
        if not text.strip():
            raise ValueError("The document appears to be empty or contains no readable text.")
            
        chunks = self.chunk_text(text)
        if not chunks:
            raise ValueError("No text chunks could be extracted from this document.")
            
        logger.info(f"DocumentRAGService: Learning {len(chunks)} chunks from '{file_name}' for chat {chat_id}...")
        
        count = 0
        for chunk in chunks:
            embedding = await self.ai_agent.get_embedding_async(chunk)
            if embedding:
                custom_char_name = f"custom_{chat_id}"
                self.lore_repo.insert_lore(chunk, embedding, custom_char_name)
                count += 1
                
        return count
