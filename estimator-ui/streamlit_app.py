
import os
import streamlit as st
import requests

API_URL = os.getenv("ESTIMATOR_URL", "http://localhost:8000")

st.title("Meeting Estimator")

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])


if prompt := st.chat_input("Paste your meeting transcription here..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    response = requests.post(
        f"{API_URL}/api/v1/estimate/stream",
        json={"transcription": prompt},
        stream=True,
    )
    # For debugging, you can uncomment the following line to see the raw response from the API, in case I face issues with the input size.
    #st.write(response.status_code, response.json())
    response.raise_for_status()
    with st.chat_message("assistant"):
        estimation = st.write_stream(response.iter_content(chunk_size=None, decode_unicode=True))

    st.session_state.messages.append({"role": "assistant", "content": estimation})