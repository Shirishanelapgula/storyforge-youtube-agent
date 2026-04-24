"""
config/prompts.py
All LLM prompt templates used across agents.
"""

STORY_GENERATION_PROMPT = """You are a master storyteller specializing in original moral fables for YouTube.

Generate a completely original moral story with the following requirements:
- Format: {format_type}  (shorts = under 60 sec narration | long = 5-10 min narration)
- Theme: {theme}
- Target audience: All ages, family-friendly
- Tone: Warm, inspiring, emotionally engaging

Return ONLY valid JSON (no markdown, no preamble) with this exact schema:
{{
  "title": "Unique story title",
  "moral": "One-sentence moral lesson",
  "setting": "Brief world/location description",
  "characters": [
    {{
      "name": "Character name",
      "role": "hero | mentor | antagonist | supporting",
      "description": "Physical appearance and personality in 2 sentences",
      "voice_trait": "e.g. calm and wise | excitable and young | gruff but kind"
    }}
  ],
  "scenes": [
    {{
      "scene_number": 1,
      "title": "Scene title",
      "narration": "Full narration text for this scene (natural spoken language)",
      "visual_description": "ENGLISH visual description: what the camera sees — characters, setting, action, lighting, camera angle. Example: A young Indian girl in orange saree standing at village well at golden hour, looking up hopefully, soft warm light",
      "emotion": "primary emotion of this scene",
      "duration_hint_sec": 10
    }}
  ],
  "call_to_action": "End-of-video CTA (subscribe, comment, etc.)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "description": "YouTube video description (SEO optimized, 150 words)"
}}

Ensure:
1. All content is 100% original — no existing fairy tales or copyrighted stories
2. Characters have unique names not from any known IP
3. Story teaches a clear moral lesson
4. Narration is conversational and engaging for voice-over
5. No violence, adult content, or controversial topics
6. Scene count: EXACTLY {scene_count} scenes
7. MANDATORY: Last scene must be a proper conclusion that:
   - Resolves the main conflict completely
   - States the moral lesson clearly
   - Gives characters a satisfying ending
   - Ends with a positive, uplifting message
   - Includes the call to action naturally
8. Never end the story mid-scene or mid-sentence
9. The final scene narration must feel like a complete ending
11. The "visual_description" field is MANDATORY in every scene.
    CRITICAL: visual_description must ALWAYS be written in ENGLISH ONLY.
    Even if the story language is Telugu or Hindi, visual_description is ALWAYS English.
    Never write visual_description in Telugu, Hindi, or any other language.
    
    Write it like a camera direction:
    "Young Indian woman in red saree helping elderly man at dusty village road, 
     warm golden sunset lighting, medium shot, other villagers watching"

12. visual_description FORMAT (always English):
    [Character appearance + clothing] + [action] + [setting/background] + [lighting] + [camera shot]
    
    CORRECT example:
    "Elderly man in white dhoti sitting alone on wooden bench, village market background,
     sad expression, soft afternoon light, medium close-up shot"
    
    WRONG example (DO NOT DO THIS):
    "వేణుగోపాల్ మంచి దుస్తులలో..." (Telugu — this is WRONG)
"""

IMAGE_PROMPT_TEMPLATE = """You are a visual artist creating scene prompts for AI image generation.

Story context:
- Title: {title}
- Setting: {setting}
- Characters: {characters}

Scene to visualize:
- Scene #{scene_number}: {scene_title}
- Visual description: {visual_description}
- Emotion: {emotion}

Create a detailed image generation prompt for this scene.
Return ONLY a single string (no JSON, no explanation) that describes the image vividly.
Include: composition, lighting, character positions, background details, art style.
Style must be: {style_suffix}
Keep under 200 words.
"""

QUALITY_CHECK_PROMPT = """You are a YouTube content policy reviewer.

Review this story for YouTube monetization compliance:
Title: {title}
Content: {content}

Check for:
1. Any copyrighted characters or stories (score 0 if found)
2. Violence, blood, weapons (score 0 if found)
3. Adult or sexual content (score 0 if found)
4. Political or religious controversy (score 0 if found)
5. Drug or alcohol glorification (score 0 if found)
6. Hate speech or discrimination (score 0 if found)
7. Originality of story (1.0 = fully original)
8. Family-friendly rating (1.0 = fully appropriate)

Return ONLY valid JSON:
{{
  "approved": true,
  "score": 0.95,
  "issues": [],
  "notes": "Brief reviewer notes"
}}
"""
