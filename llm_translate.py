import tiktoken
import openai
import logging
from tqdm import tqdm
import os
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_tokenizer():
    """Initialize and return the GPT-4 tokenizer."""
    logger.debug("Initializing GPT-4 tokenizer")
    return tiktoken.encoding_for_model("gpt-4o")

def tokenize_text(text, tokenizer):
    """Tokenize the input text using the provided tokenizer."""
    logger.debug(f"Tokenizing text of length {len(text)}")
    return tokenizer.encode(text)

def split_into_chunks(tokens, max_tokens=20000, overlap=500):
    """Split tokens into chunks with overlap."""
    logger.info(f"Splitting {len(tokens)} tokens into chunks (max_tokens={max_tokens}, overlap={overlap})")
    chunks = []
    start = 0
    with tqdm(total=len(tokens), desc="Splitting into chunks"):
        while start < len(tokens):
            end = start + max_tokens
            if end >= len(tokens):
                chunks.append(tokens[start:])
                start = len(tokens) + 1
            else:
                last_period = find_last_period(tokens, start, end, overlap)
                chunks.append(tokens[start:last_period])
                start = last_period
    logger.info(f"Split into {len(chunks)} chunks")
    return chunks

def find_last_period(tokens, start, end, overlap):
    """Find the last period within the overlap region."""
    tokenizer = get_tokenizer()
    overlap_start = max(start, end - overlap)
    overlap_end = min(end + overlap, len(tokens))
    for i in range(overlap_end - 1, overlap_start - 1, -1):
        if tokenizer.decode([tokens[i]]) == '.':
            return i + 1
    return overlap_end

def translate_chunk(chunk_text, target_language, context="", llm_name='gpt-4o-mini'):
    """Translate a single chunk of text."""
    llm = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"), http_client=httpx.Client(proxy=os.getenv("PROXY_URL")), base_url=os.getenv("BASE_URL"))

    prompt = f"{context}Translate the following text to {target_language}: {chunk_text}"
    
    try:
        logger.debug(f"Sending translation request for chunk of length {len(chunk_text)}")
        response = llm.chat.completions.create(
            model=llm_name,
            messages=[
                {"role": "system", "content": f"You are an expert translator with fluency in German, French, English and Italian languages. Translate the given text to {target_language}. For German output use Swiss German writing, i.e. use ss instead of ß."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1
        )
        translated_text = response.choices[0].message.content.strip()
        logger.debug(f"Received translation of length {len(translated_text)}")
        return translated_text
    except openai.OpenAIError as e:
        logger.error(f"An error occurred while translating: {e}")
        return None

def translate_chunks(chunks, target_language, tokenizer, llm):
    """Translate all chunks and maintain context between them."""
    translated_chunks = []
    logger.info(f"Translating {len(chunks)} chunks to {target_language}")
    with tqdm(total=len(chunks), desc="Translating chunks") as pbar:
        for i, chunk in enumerate(chunks):
            chunk_text = tokenizer.decode(chunk)
            context = ""
            if i > 0:
                context = f"Previous translated text as context: {translated_chunks[-1][-100:]}\n\n"
            
            translated_chunk = translate_chunk(chunk_text, target_language, context, llm)
            if translated_chunk:
                translated_chunks.append(translated_chunk)
                pbar.update(1)
            else:
                logger.error(f"Translation failed for chunk {i}")
                return None
    return translated_chunks

def combine_translations(translated_chunks):
    """Combine translated chunks into a single text."""
    logger.info(f"Combining {len(translated_chunks)} translated chunks")
    final_translation = " ".join(translated_chunks)
    if len(final_translation) == 0:
        raise ValueError("Produced an empty translation.")
    return final_translation

def chunk_and_translate(text, target_language, max_tokens=20000, overlap=500, llm="gpt-4o-mini"):
    """Main function to chunk, translate, and combine text."""
    logger.info(f"Starting translation process for text of length {len(text)} to {target_language}")
    tokenizer = get_tokenizer()
    tokens = tokenize_text(text, tokenizer)
    chunks = split_into_chunks(tokens, max_tokens, overlap)
    translated_chunks = translate_chunks(chunks, target_language, tokenizer, llm)
    if translated_chunks:
        final_translation = combine_translations(translated_chunks)
        logger.info(f"Translation completed. Final length: {len(final_translation)}")
        return final_translation
    logger.error("Translation process failed")
    return None