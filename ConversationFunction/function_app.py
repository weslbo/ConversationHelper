import azure.functions as func
import logging
import os, fnmatch
import requests
import markdownify
import re
import json
import azure.cognitiveservices.speech as speechsdk
import shutil
import io
import mimetypes
from fastapi import FastAPI, Request, Response 
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from bs4.element import Comment
from urllib.parse import urljoin
from openai import AzureOpenAI
from pydub import AudioSegment
from pydub.playback import play


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


def tag_visible(element):
    if element.parent.name in ['style', 'script', 'head', 'title', 'meta', '[document]']:
        return False
    if isinstance(element, Comment):
        return False
    return True

def calculate_number_words(text): 
    nrOfWords = len(text.split())
    return nrOfWords

def calculate_approx_tokens(text):
    nrOfTokens = round(calculate_number_words(text) * 3)
    if nrOfTokens > 13000:
        nrOfTokens = 13000
    return nrOfTokens

@app.route(route="retrieve_conversation")
def retrieve_conversation(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Starting conversation function.')

    host = "Brian"
    guest = "Emma"

    logging.info('1. retrieving environment variables')
    load_dotenv()

    url = req.params.get('url')
    if not url:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            url = req_body.get('url')

    logging.info('2. retrieving content from URL: ' + url)

    if url:
        response = requests.get(url)

        logging.info('3. parsing content using BeatifulSoup')
        soup = BeautifulSoup(response.text, 'html.parser')

        # might need to adapt this when working with other web pages (not Microsoft Learn)
        div = soup.find(id="unit-inner-section")

        if not div is None:
            logging.info('3a. cleaning up the content')
            for ul in div.find_all("ul", class_="metadata"):
                ul.decompose()
            for d in div.find_all("div", class_="xp-tag"):
                d.decompose()
            for next in div.find_all("div", class_="next-section"):
                next.decompose()
            for header in div.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
                header.string = "\n# " + header.get_text() + "\n"
            for code in div.find_all("code"):
                code.decompose()

        logging.info('4. retrieving visible text from content')
        texts = soup.findAll(text=True)
        visible_texts = filter(tag_visible, texts)  
        text = u" ".join(t.strip() for t in visible_texts)

        #logging.info('5. converting content (size: ' + len(text) + ') to markdown')
        #markdown = markdownify.markdownify(text, heading_style="ATX", bullets="-")
        #markdown = re.sub('\n{3,}', '\n\n', markdown)
        #markdown = markdown.replace("[Continue](/en-us/)", "")

        logging.info(f'4a. calculating number of approx tokens {calculate_approx_tokens(text)}')

        logging.info('5. calling azure openai')
        client = AzureOpenAI(azure_endpoint=os.getenv("AZURE_ENDPOINT"), api_version="2023-07-01-preview", api_key=os.getenv("OPENAI_API_KEY"))
        message_text = [
            {"role":"system","content":"""
                You're going to create a transcript for an engaging conversation between Brian and Andrew, based on the content below. 
                Do not talk about any other topic.
                Transform the text to the Speech Syntheses Markup Language.  
                - [Brian] should use the voice with name en-US-BrianNeural
                - [Andrew] should use the voice with name en-US-AndrewNeural
                - There is no need for introductions anymore. No "welcome" needed.
                - The output should be XML.
                - Make sure that every line is wrapped between <voice> and </voice> element.                
                - Finally, make sure there is the following element at the start: <speak xmlns""http://www.w3.org/2001/10/synthesis"" xmlns:mstts=""http://www.w3.org/2001/mstts"" xmlns:emo=""http://www.w3.org/2009/10/emotionml"" version=""1.0"" xml:lang=""en-US"">
                - End the XML document with the following element: </speak>
                - Delete [Brian]: and [Andrew]: from the transcript.
                ------------""" + text},
            {"role":"user","content":"generate the conversation"}
        ]
        completion = client.chat.completions.create(
            model="gpt-35-turbo-16k",
            messages = message_text,
            temperature=0.1,
            max_tokens=8000,
            top_p=0.95,
            frequency_penalty=0,
            presence_penalty=0,
            stop=None
        )

        logging.info(f'5a. tokens used: {completion.usage.total_tokens}')

        logging.info('6. converting response to SSML')
        ssml = completion.choices[0].message.content

        service_region = "eastus"
        speech_key = os.getenv("SPEECH_API_KEY")
        speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=service_region)
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Audio24Khz96KBitRateMonoMp3)  

        filename = "conversation.mp3"
        file_config = speechsdk.audio.AudioOutputConfig(filename=filename)
        speech_synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=file_config)  
        result = speech_synthesizer.speak_ssml_async(ssml).get()

        logging.info('7. return audio/mpeg')
        with open(filename, 'rb') as f:
            mimetype = mimetypes.guess_type(filename)
            return func.HttpResponse(f.read(), mimetype=mimetype[0])
        
        #return Response(content=stream, media_type="audio/mpeg") 
    else:
        return func.HttpResponse(
             "This HTTP triggered function executed successfully. Pass a name in the query string or in the request body for a personalized response.",
             status_code=200
        )